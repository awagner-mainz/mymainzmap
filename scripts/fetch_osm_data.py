#!/usr/bin/env python3
"""
Fetch facility data for Mainz from the OpenStreetMap Overpass API and write
it out as a single GeoJSON FeatureCollection at data/facilities.geojson.

Categories are read from categories.json so that adding a new facility type
only requires editing that file (add the OSM tag there, it gets picked up
here automatically).

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

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Mainz's administrative area, resolved by name rather than a hardcoded
# relation id, so the query always matches the city's real boundary as
# currently mapped in OSM. Rhineland-Palatinate kreisfreie Städte (like
# Mainz) are admin_level=6; see https://wiki.openstreetmap.org/wiki/Tag:boundary=administrative
# for the per-country admin_level table if you adapt this for another city.
AREA_NAME = "Mainz"
AREA_ADMIN_LEVEL = "6"

REQUEST_TIMEOUT = 180
MAX_RETRIES = 3


def load_categories() -> dict:
    with open(CATEGORIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_query(categories: dict) -> str:
    """Build one Overpass QL query covering every category in categories.json."""
    clauses = []
    for tag in categories:
        key, value = tag.split("=", 1)
        # node/way/relation so that e.g. leisure=park polygons are included
        # (`out center` below returns a representative point for them).
        clauses.append(f'node["{key}"="{value}"](area.mainz);')
        clauses.append(f'way["{key}"="{value}"](area.mainz);')
        clauses.append(f'relation["{key}"="{value}"](area.mainz);')

    return f"""
    [out:json][timeout:{REQUEST_TIMEOUT}];
    area["boundary"="administrative"]["admin_level"="{AREA_ADMIN_LEVEL}"]["name"="{AREA_NAME}"]->.mainz;
    (
      {" ".join(clauses)}
    );
    out center tags;
    """


def category_for_tags(tags: dict, categories: dict) -> str | None:
    for tag in categories:
        key, value = tag.split("=", 1)
        if tags.get(key) == value:
            return tag
    return None


def element_to_feature(element: dict, categories: dict) -> dict | None:
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
        "category": category,
        "name": tags.get("name", categories[category]["label"]),
        "osm_type": element["type"],
        "osm_id": element["id"],
    }
    # Pass through a few commonly-useful extra attributes, if present.
    for key in ("opening_hours", "wheelchair", "image", "wikimedia_commons"):
        if key in tags:
            properties[key] = tags[key]

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def fetch_overpass(query: str) -> dict:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                OVERPASS_URL, data={"data": query}, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            print(f"Attempt {attempt} failed: {exc}", file=sys.stderr)
            time.sleep(10 * attempt)
    raise RuntimeError(f"Overpass request failed after {MAX_RETRIES} attempts") from last_error


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
