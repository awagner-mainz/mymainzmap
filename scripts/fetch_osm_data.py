#!/usr/bin/env python3
"""
Fetch facility data for Mainz from the OpenStreetMap Overpass API and write
it out as a single GeoJSON FeatureCollection at data/facilities.geojson.

Categories are read from categories.json so that adding a new facility type
only requires editing that file. Each category has a `match` list of
{key, value} tag conditions that must ALL be present on an OSM element
(AND, not OR) — this is what lets you query on more than one attribute at
once, e.g. amenity=fountain AND drinking_water=yes for "fountains that are
also drinking water sources", as opposed to amenity=drinking_water
(dedicated drinking-water taps) which is a separate category.

Every OSM tag on a matched element (minus a short deny-list of purely
editorial/meta tags) is passed through to the GeoJSON feature's properties,
so index.html can display whatever attributes happen to exist — OSM has no
fixed schema, so "all available attributes" varies per feature; there's no
way to know the full set in advance except by checking the relevant OSM
wiki tag page for typical combinable tags, e.g.
https://wiki.openstreetmap.org/wiki/Tag:amenity=drinking_water

Docs:
  Overpass QL:    https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
  Overpass API:   https://dev.overpass-api.de/overpass-doc/en/
  OSM map features: https://wiki.openstreetmap.org/wiki/Map_features
"""

import json
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATEGORIES_PATH = ROOT / "categories.json"
OUTPUT_PATH = ROOT / "data" / "facilities.geojson"

# overpass-api.de's main instance has been intermittently rejecting
# requests with 406 Not Acceptable amid heavy load (see
# https://github.com/drolbr/Overpass-API/issues/791 and
# https://community.openstreetmap.org/t/overpass-api-error-406/143198),
# and overpass.private.coffee has in turn been seen timing out (504) under
# its own load. We fail over across full-planet public instances from
# https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances
# — deliberately excluding region-limited mirrors like overpass.osm.ch
# (Switzerland-only data): a regional mirror would return an empty result
# instead of an error for a Mainz query, which is a worse failure mode
# than a visible one.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

# Overpass's usage policy asks every client to identify itself so operators
# can get in touch if something's wrong — a generic "python-requests/x.x"
# User-Agent is exactly what's getting caught by the current anti-scraper
# filtering. Put your own contact info here (an email, or your repo URL).
USER_AGENT = "mainz-facilities-map/1.0 (https://github.com/YOUR_USERNAME/YOUR_REPO)"

# Mainz's administrative area, resolved by name rather than a hardcoded
# relation id, so the query always matches the city's real boundary as
# currently mapped in OSM. Rhineland-Palatinate kreisfreie Städte (like
# Mainz) are admin_level=6; see https://wiki.openstreetmap.org/wiki/Tag:boundary=administrative
# for the per-country admin_level table if you adapt this for another city.
AREA_NAME = "Mainz"
AREA_ADMIN_LEVEL = "6"

REQUEST_TIMEOUT = 180
MAX_RETRIES = 2  # per instance — kept low so a down mirror fails over quickly

# Editorial/meta tags that aren't useful facility info for an end user —
# omitted when passing through OSM tags to the GeoJSON properties. Prefix
# matched, so "source" also excludes "source:date", "source:geometry", etc.
EXCLUDED_TAG_PREFIXES = ("source", "created_by", "fixme", "todo")


def load_categories() -> list:
    """Returns just the flat category list — the fetch/query logic here
    doesn't care about groups or default_enabled, those are purely a
    display concern handled in index.html."""
    with open(CATEGORIES_PATH, encoding="utf-8") as f:
        return json.load(f)["categories"]


def build_query(categories: list) -> str:
    """Build one Overpass QL query covering every category in categories.json.

    Each category's `match` conditions are chained as consecutive bracket
    filters, e.g. match=[{amenity:fountain},{drinking_water:yes}] becomes
    ["amenity"="fountain"]["drinking_water"="yes"] — Overpass QL combines
    consecutive filters with AND, which is exactly "has this tag AND that
    tag". There's no direct OR between different tags in a single filter
    chain; if you need that, run a separate clause per alternative (like
    the toilets/drinking_water/etc. categories already do relative to each
    other) — see https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
    for the full filter syntax (key existence, regex, negation, etc.).
    """
    clauses = []
    for cat in categories:
        conditions = "".join(
            f'["{m["key"]}"="{m["value"]}"]' for m in cat["match"]
        )
        # node/way/relation so that e.g. leisure=park polygons are included
        # (`out center` below returns a representative point for them).
        for elem_type in ("node", "way", "relation"):
            clauses.append(f"{elem_type}{conditions}(area.mainz);")

    return f"""
    [out:json][timeout:{REQUEST_TIMEOUT}];
    area["boundary"="administrative"]["admin_level"="{AREA_ADMIN_LEVEL}"]["name"="{AREA_NAME}"]->.mainz;
    (
      {" ".join(clauses)}
    );
    out center tags;
    """


def category_for_tags(tags: dict, categories: list) -> dict | None:
    """First category (in categories.json order) whose match conditions are
    all satisfied by this element's tags. Put more specific categories
    before more general ones in categories.json if they could overlap."""
    for cat in categories:
        if all(tags.get(m["key"]) == m["value"] for m in cat["match"]):
            return cat
    return None


def passthrough_tags(tags: dict) -> dict:
    return {
        k: v
        for k, v in tags.items()
        if not any(k == p or k.startswith(p + ":") for p in EXCLUDED_TAG_PREFIXES)
    }


def element_to_feature(element: dict, categories: list) -> dict | None:
    tags = element.get("tags", {})
    category = category_for_tags(tags, categories)
    if category is None:
        return None

    if element["type"] == "node":
        lon, lat = element["lon"], element["lat"]
    else:
        # ways/relations: Overpass gives a `center` point when we ask for
        # `out center`
        center = element.get("center")
        if not center:
            return None
        lon, lat = center["lon"], center["lat"]

    properties = {
        # Every OSM tag on this element (minus the deny-list) first, then
        # our computed fields — ordered this way so a raw tag can never
        # accidentally clobber one of these.
        **passthrough_tags(tags),
        "category": category["id"],
        "name": tags.get("name", category["label"]),
        "osm_type": element["type"],
        "osm_id": element["id"],
    }

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def fetch_overpass(query: str) -> dict:
    last_error = None
    headers = {"User-Agent": USER_AGENT}

    for url in OVERPASS_URLS:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"Querying {url} (attempt {attempt})...")
                response = requests.post(
                    url, data={"data": query}, headers=headers, timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                print(f"  failed: {exc}", file=sys.stderr)
                time.sleep(10 * attempt)
        print(f"Giving up on {url}, trying next instance if any remain.", file=sys.stderr)

    raise RuntimeError(
        f"Overpass request failed on all {len(OVERPASS_URLS)} instances"
    ) from last_error


def main() -> None:
    categories = load_categories()
    query = build_query(categories)

    print("Querying Overpass API for Mainz facilities...")
    data = fetch_overpass(query)

    features = []
    for element in data.get("elements", []):
        feature = element_to_feature(element, categories)
        if feature is not None:
            features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "OpenStreetMap contributors, via Overpass API",
            "license": "ODbL 1.0 - https://opendatacommons.org/licenses/odbl/",
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "feature_count": len(features),
        },
        "features": features,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(features)} features to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
