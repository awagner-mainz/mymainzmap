# Mainz public facilities map

A Leaflet map of public toilets, drinking fountains, benches, playgrounds
and parks in Mainz, sourced from OpenStreetMap.

## How it fits together

- **`categories.json`** — the one file to edit to add a new facility type.
  Maps an OSM tag (`key=value`) to a label, color and marker symbol.
- **`data/facilities.geojson`** — OSM-derived data. Regenerated automatically
  by the scheduled GitHub Action (see below) — don't hand-edit it, your
  changes will be overwritten on the next run.
- **`data/custom-places.geojson`** — hand-maintained overlay for anything
  not (yet) mapped in OSM. Add attributes freely here (photo URLs,
  descriptions, opening hours) — any property you add shows up in the
  marker popup automatically.
- **`scripts/fetch_osm_data.py`** — queries the
  [Overpass API](https://dev.overpass-api.de/overpass-doc/en/) for every
  category in `categories.json` and writes `data/facilities.geojson`.
- **`.github/workflows/update-data.yml`** — runs that script every Monday
  (GitHub Actions' own
  [`schedule` trigger](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule),
  no separate server needed) and commits the result if it changed.
- **`index.html`** — the map itself: Leaflet, category filters, GPS locate
  control, and Leaflet.EdgeMarker for off-screen indicators.

## Adding a facility category

1. Add an entry to `categories.json`, e.g.:
   ```json
   "amenity=bicycle_parking": { "label": "Bike parking", "color": "#6C5B7B", "symbol": "P" }
   ```
2. Look up the correct OSM tag on the
   [Map Features wiki](https://wiki.openstreetmap.org/wiki/Map_features)
   if you're not sure of the exact key/value.
3. Either wait for the next scheduled run, or trigger it manually from the
   repo's **Actions** tab → "Update facilities data from OpenStreetMap" →
   **Run workflow**.

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

## Map tiles: hosted OSM tiles

`index.html` uses hosted `tile.openstreetmap.org` tiles directly. This is
allowed under the
[OSM Foundation's tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
as long as usage stays interactive and modest: no bulk downloading or tile
archiving, no headless/scripted panning, and visible attribution kept on
the map (already wired up via `mapAttribution` in `index.html`). A small
personal project's normal traffic fits comfortably within that. The
tradeoff you're accepting: the policy also says access can be throttled or
blocked without notice if usage patterns look automated or grow
unexpectedly, since the tile servers run on donated capacity — there's no
SLA.

### If OSM tile access gets cut off

Swap the single `L.tileLayer(...)` call in `index.html` for one of these —
nothing else in the app needs to change, since Leaflet's tile layer API is
the same regardless of provider.

**Option A — a hosted third-party provider** (quickest migration, still
no server to run):
```js
// e.g. MapTiler or Stadia Maps, both have a free tier and give you an API key
L.tileLayer("https://api.maptiler.com/maps/streets/{z}/{x}/{y}.png?key=YOUR_KEY", {
  attribution: mapAttribution,
  maxZoom: 19,
}).addTo(map);
```

**Option B — self-hosted static tiles**, using a downloaded extract such
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
- [Leaflet.EdgeMarker](https://github.com/ubergesundheit/Leaflet.EdgeMarker) —
  shows arrows at the map edge pointing toward markers outside the current view
- [leaflet-locatecontrol](https://github.com/domoritz/leaflet-locatecontrol) —
  the GPS "find me" button, uses the browser's
  [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API)
  under the hood (requires HTTPS, which GitHub Pages provides automatically)
