# Country boundaries

`country-boundaries.json` is derived from Natural Earth Vector's 1:50m Admin 0
map units, version 5.1.1. Only features with valid two-letter `ISO_A2_EH`
country codes are retained. Each feature exposes the Natural Earth `NAME` as
`name` and `ISO_A2_EH` as `country_code`. The source was simplified to 50% with
Mapshaper and coordinate precision was limited to four decimal places.

- Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_50m_admin_0_map_units.geojson
- Terms: https://www.naturalearthdata.com/about/terms-of-use/

Natural Earth data is in the public domain.
