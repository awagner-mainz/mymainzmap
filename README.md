# Mainz public facilities map

A Leaflet map of public toilets, drinking fountains, benches, playgrounds
and parks in Mainz, sourced from OpenStreetMap.

## How it fits together

- **`categories.json`** — the one file to edit to add a new facility type.
  An array of categories, each with an `id`, `label`, `color`, `symbol`,
  and a `match` list of OSM tags that must **all** be present (AND) for an
  element to count as that category.
- **`data/facilities.geojson`** — OSM-derived data. Regenerated automatically
  by the scheduled GitHub Action (see below) — don't hand-edit it, your
  changes will be overwritten on the next run.
- **`data/custom-places.geojson`** — hand-maintained overlay for anything
  not (yet) mapped in OSM. Add attributes freely here (photo URLs,
  descriptions, opening hours, anything) — any property you add shows up in
  the marker popup automatically.
- **`scripts/fetch_osm_data.py`** — queries the
  [Overpass API](https://dev.overpass-api.de/overpass-doc/en/) for every
  category in `categories.json` and writes `data/facilities.geojson`.
- **`.github/workflows/update-data.yml`** — runs that script every Monday
  (GitHub Actions' own
  [`schedule` trigger](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule),
  no separate server needed) and commits the result if it changed.
- **`index.html`** — the map itself: Leaflet, category filters, and a GPS
  locate control. Markers are pins (`L.divIcon`).

## Adding a facility category

1. Add an entry to `categories.json`, e.g.:
   ```json
   {
     "id": "bicycle_parking",
     "label": "Bike parking",
     "color": "#6C5B7B",
     "symbol": "P",
     "match": [{ "key": "amenity", "value": "bicycle_parking" }]
   }
   ```
2. Look up the correct OSM tag on the
   [Map Features wiki](https://wiki.openstreetmap.org/wiki/Map_features)
   if you're not sure of the exact key/value.
3. Either wait for the next scheduled run, or trigger it manually from the
   repo's **Actions** tab → "Update facilities data from OpenStreetMap" →
   **Run workflow**.

## Querying by more than one attribute

`match` can list more than one `{key, value}` pair — an element only
counts as that category if it has **all** of them. This is how you'd tell
apart, say, decorative fountains from fountains that are also a drinking
water source: in OSM these are the same base tag (`amenity=fountain`) with
an additional `drinking_water=yes` sub-tag when it applies (see
[Key:drinking_water](https://wiki.openstreetmap.org/wiki/Key:drinking_water)).
`categories.json` already has a working example:
```json
{
  "id": "fountain_drinking",
  "label": "Fountain (drinking water)",
  "color": "#0FB5AE",
  "symbol": "W",
  "match": [
    { "key": "amenity", "value": "fountain" },
    { "key": "drinking_water", "value": "yes" }
  ]
}
```
This becomes the Overpass QL filter chain
`["amenity"="fountain"]["drinking_water"="yes"]` — consecutive bracket
filters are ANDed together automatically. If a category earlier in the
list would also match the same element, that earlier one wins (categories
are checked in file order) — keep more specific categories above more
general ones if they could overlap.

What `match` can't do: OR across different tags, or `!=`/regex conditions.
Overpass QL supports those too (`[key]` for "has this key regardless of
value", `[key!=value]`, `[key~"regex"]`, and a `union` of separate clauses
in parentheses for OR) — see the
[Overpass QL reference](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL#Tag_filters)
for the full syntax. `categories.json`'s schema only covers the common
AND-of-exact-values case; anything beyond that means hand-editing the
`build_query()` function in `scripts/fetch_osm_data.py` for that one
category, following the same pattern as the existing loop.

## Attributes in the marker popup

OSM has no fixed schema — any node can carry any tag, and which ones
actually exist varies per feature (a bench might have `material` and
`backrest`; a drinking fountain might have `bottle` and `check_date`).
Because of that, `fetch_osm_data.py` doesn't use an allowlist: it passes
through **every** OSM tag on a matched element into the GeoJSON feature's
properties, except for a short deny-list of purely editorial/meta tags
(`source`, `created_by`, `fixme`, `todo`, and their `key:subkey` variants)
defined in `EXCLUDED_TAG_PREFIXES` near the top of that script — edit that
list if you want to hide (or stop hiding) something.

In `index.html`, `popupContent()` gives a few fields their own line
(`name`, `description`, `opening_hours`, a photo/`image`), and puts
everything else under a collapsed "More details" section automatically —
so a new tag doesn't need any code change to show up, it just appears
there with its key prettified (`drinking_water` → "Drinking water").
`website`/`contact:website` and `phone`/`contact:phone` are rendered as
clickable links; add more keys to `LINK_KEYS`/`PHONE_KEYS` in `index.html`
for the same treatment, or to `POPUP_HANDLED_KEYS` to give a tag its own
dedicated line instead of leaving it in the generic list.

There's no way to know in advance every attribute a given OSM tag *could*
have — the closest thing is each tag's wiki page, which documents commonly
combined sub-tags, e.g.
[Tag:amenity=drinking_water](https://wiki.openstreetmap.org/wiki/Tag:amenity=drinking_water)
lists `bottle`, `fee`, `check_date`, `wheelchair` and others as tags people
commonly add alongside it — but nothing enforces that any particular one
is present on any particular node.

## Adding a place that's missing from OSM

Two options:

- **Recommended: add it to OSM directly** via the
  [iD editor](https://wiki.openstreetmap.org/wiki/ID) (a couple of clicks
  in the browser, no account setup beyond a free OSM login). It'll appear
  in your map automatically on the next data refresh, and every other app
  built on OSM benefits too.
- **Quick/temporary: add it to `data/custom-places.geojson`** as a new
  GeoJSON Feature with a `category` matching one of your `categories.json`
  keys.

## Running the fetch script locally

```bash
pip install requests
python scripts/fetch_osm_data.py
```

Before running it for real, edit `USER_AGENT` near the top of
`scripts/fetch_osm_data.py` to point at something that identifies you —
your repo URL or an email address. Overpass's usage policy asks for this
so operators can reach you if there's a problem; it also happens to be
what protects you from some of the current anti-scraper filtering (see
below).

### About the Overpass 406 errors

`overpass-api.de`'s main instance has been intermittently returning `406
Not Acceptable` under heavy load — this is a known, widely-reported
issue (see [drolbr/Overpass-API#791](https://github.com/drolbr/Overpass-API/issues/791)),
not something specific to this query. The script sends a proper
identifying `User-Agent` and fails over across a short list of public
[Overpass instances](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances)
to work around it. If all of them fail, wait a bit and re-run — or add
another instance from that wiki list to `OVERPASS_URLS`.

## Deploying to GitHub Pages

1. Push this repo to GitHub.
2. Repo **Settings → Pages → Source**: deploy from the `main` branch
   (root).
3. The Action needs no secrets — it uses the default `GITHUB_TOKEN`, which
   already has write access to the repo it runs in.

## Map tiles: CARTO Positron

`index.html` uses [CARTO Positron](https://github.com/CartoDB/basemap-styles)
tiles — a plain, label-only basemap (streets, building outlines, place
names) with no baked-in shop/amenity icons. This was a deliberate switch
away from plain OSM-Carto tiles (`tile.openstreetmap.org`): that style
renders POI icons — restaurants, shops, pharmacies — directly into the
tile image pixels, which isn't something the app can filter or turn off;
there's no layer to toggle, since it's part of the basemap's own opinion
about what to show. Positron is designed for exactly this use case:
overlaying your own point data without competing icon clutter. It also
takes some load off OSM's own donated tile servers, a nice side effect
though not the primary reason for the switch.

CARTO's basemap service is free, with its own best-effort, no-SLA terms
(see [carto.com/attributions](https://carto.com/attributions)) similar in
spirit to the [OSM Foundation's tile policy](https://operations.osmfoundation.org/policies/tiles/).
This site's traffic — small, interactive-only, normal pan/zoom, no
pre-fetching or headless rendering — fits comfortably within that.

### If your tile provider gets cut off

Swap the single `L.tileLayer(...)` call in `index.html` for one of these —
nothing else in the app needs to change, since Leaflet's tile layer API is
the same regardless of provider.

**Option A — hosted OSM tiles** (brings back the shop/POI icon clutter,
but is a quick way to confirm the map itself still works):
```js
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);
```

**Option B — another hosted provider with a clean/label-only style**
(quickest migration that keeps the icon-free look, still no server to
run):
```js
// e.g. MapTiler or Stadia Maps, both have a free tier and give you an API key
L.tileLayer("https://api.maptiler.com/maps/streets/{z}/{x}/{y}.png?key=YOUR_KEY", {
  attribution: mapAttribution,
  maxZoom: 19,
}).addTo(map);
```

**Option C — self-hosted static tiles**, using a downloaded extract such
as [MapTiler's Mainz on-prem dataset](https://www.maptiler.com/on-prem-datasets/europe/germany/mainz/):

1. That download is typically an **MBTiles** file (a single SQLite
   database of tiles). GitHub Pages can only serve static files, so unpack
   it into a plain folder of `{z}/{x}/{y}.png` files first, using
   [MBUtil](https://github.com/mapbox/mbutil):
   ```bash
   pip install mbutil
   mb-util --image_format=png your-mainz-extract.mbtiles tiles/
   ```
2. Commit the resulting `tiles/` folder to the repo (or a `gh-pages`-only
   branch, if you'd rather keep it out of `main`'s history).
3. Point the tile layer at the local path:
   ```js
   L.tileLayer("tiles/{z}/{x}/{y}.png", { attribution: mapAttribution, maxZoom: 19 }).addTo(map);
   ```
4. Check the license terms that came with your MapTiler download for the
   required attribution text and use it in `mapAttribution`.

If MapTiler offers a **PMTiles** export instead, that format is designed
to be served directly over plain HTTP range requests with no unpacking
step — see [docs.protomaps.com/pmtiles](https://docs.protomaps.com/pmtiles/) —
but you'd swap Leaflet for [MapLibre GL JS](https://maplibre.org/) to read
it, which is a bigger change than a drop-in tile URL swap.

## Licensing note

Mainz's own official geodata (e.g. the city base map served via its
WebGIS) is published under a **CC BY-NC-ND** license in the national
geodata catalog — no derivatives allowed, so it's not usable as a source
for this kind of republished dataset. OpenStreetMap data is
[ODbL-licensed](https://opendatacommons.org/licenses/odbl/) instead, which
is why this project sources facility data from there rather than from the
city directly. Keep the OSM attribution shown in the map's bottom-right
corner intact — it's required by the license.

## Libraries used

- [Leaflet](https://leafletjs.com/reference.html)
- [leaflet-locatecontrol](https://github.com/domoritz/leaflet-locatecontrol) —
  the GPS "find me" button, uses the browser's
  [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API)
  under the hood (requires HTTPS, which GitHub Pages provides automatically)

## Leaflet.EdgeMarker — disabled

[Leaflet.EdgeMarker](https://github.com/ubergesundheit/Leaflet.EdgeMarker)
(shows arrows at the map edge pointing toward markers outside the current
view) was in an earlier version of this project but has been removed. It
draws one indicator per off-screen marker — fine for a handful of
features, but with a city-wide dataset (hundreds of benches alone once
real OSM data replaced the placeholder sample), the large number of
off-screen markers at typical zoom levels produced a dense, visually
corrupted mass of overlapping indicators piling up at the viewport edges,
persisting and relocating oddly as the map was zoomed. Switching marker
rendering (canvas vs. DOM) made no difference, which pointed at
EdgeMarker's own per-off-screen-marker rendering rather than the markers
themselves.

If you want off-screen indicators back, it'd need to be scoped so it
doesn't try to render hundreds of icons at once — for example, only
enabling it for a single category at a time with a naturally small count
(like `leisure=park`), or writing a custom indicator that shows a single
"N facilities off-screen, this direction" badge instead of one icon per
feature.
