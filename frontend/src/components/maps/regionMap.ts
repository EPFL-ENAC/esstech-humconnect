import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';

export type RegionCode = string;

export interface RegionData {
    properties: Record<string, number>;
}

export type DataByRegion = Record<RegionCode, RegionData>;

export interface PopupRegion {
    code: RegionCode;
    feature: Feature<Geometry, GeoJsonProperties>;
    displayedValue: number;
}

export type CreatePopupContent = (
    region: PopupRegion,
    data: RegionData | undefined,
) => HTMLElement | null;

export type RegionFeatureCollection = FeatureCollection<Geometry, GeoJsonProperties>;
