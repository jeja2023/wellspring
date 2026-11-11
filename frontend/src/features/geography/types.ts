export type ResourceType = 'PLACE'|'INCIDENT'|'WASTEWATER'
export type GeoResource = {resource_type:ResourceType;resource_id:string;name:string;code?:string;address?:string;state?:string;place_id:string|null;longitude:number|null;latitude:number|null;version:number;source:string}
export type MapConfig = {coordinate_system:'WGS84';tiles_available:boolean;attribution:string;layers:ResourceType[]}
export type Page<T> = {items:T[];page:number;total:number}
export type MapPoints = {items:GeoResource[];total:number;truncated:boolean;limit:number}
export const layerNames:Record<ResourceType,string> = {PLACE:'重点场所',INCIDENT:'场所事件',WASTEWATER:'污水采样点'}
export const layerColors:Record<ResourceType,string> = {PLACE:'#0e7770',INCIDENT:'#b77726',WASTEWATER:'#296ba1'}
