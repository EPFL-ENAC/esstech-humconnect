import type { StyleSpecification } from 'maplibre-gl';

const swissOsmAttribution =
    'Data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>, map CC BY <a href="https://github.com/xyztobixyz/OSM-Swiss-Style" target="_blank" rel="noopener noreferrer">xyztobixyz</a>, elevation: ASTER GDEM, EarthEnv-DEM90, CDEM contains information under OGL Canada';

export function createLightMapStyle(): StyleSpecification {
    return {
        version: 8,
        sources: {
            osm: {
                type: 'raster',
                tiles: ['https://tile.osm.ch/osm-swiss-style/{z}/{x}/{y}.png'],
                tileSize: 256,
                minzoom: 0,
                maxzoom: 20,
                attribution: swissOsmAttribution,
            },
        },
        layers: [
            {
                id: 'light',
                type: 'raster',
                source: 'osm',
                paint: {
                    'raster-saturation': -0.9,
                    'raster-brightness-min': 0.2,
                },
            },
        ],
    };
}
