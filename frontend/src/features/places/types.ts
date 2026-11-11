export type PlaceFields={code:string;name:string;kind:string;district:string;address:string;responsible:string;management_basis:string;review_on:string|null}
export type Place=PlaceFields&{id:string;active:boolean;version:number;updated_at:string;created_at:string;open_inspections?:number;open_incidents?:number}
export type Inspection={id:string;place_id:string;inspected_on:string;findings:string;due_on:string|null;status:string;result_note:string;version:number}
export type Incident={id:string;place_id:string;title:string;occurred_at:string;source:string;facts:string;material_ref:string;status:string;disposition:string;clue_id:string|null;version:number}
export type History={id:string;action:string;note:string;created_at:string;snapshot:unknown}
export type Page<T>={items:T[];page:number;total:number}
export const kinds:Record<string,string>={APARTMENT:'公寓',BAR:'酒吧',ENTERTAINMENT:'娱乐场所',STREET:'街区',OTHER:'其他场所'}
export const statuses:Record<string,string>={DRAFT:'待核验',RETURNED:'退回补充',OPEN:'待处置',SUBMITTED:'待复核办结',CLOSED:'已办结',DONE:'已完成'}
export const actions:Record<string,string>={CREATED:'建立场所',UPDATED:'更正场所资料',STATE_CHANGED:'启停调整',INSPECTED:'登记巡查',INSPECTION_COMPLETED:'复查整改',INCIDENT_CREATED:'登记事件',INCIDENT_UPDATED:'补充事件',INCIDENT_CONFIRM:'核验确认',INCIDENT_RETURN:'退回补充',INCIDENT_SUBMIT:'提交处置反馈',INCIDENT_CLOSE:'复核办结',INCIDENT_REOPEN:'重新办理',INCIDENT_CLUE_CREATED:'转录线索草稿'}
export function today(){const date=new Date();return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`}

export type ActionSpec={title:string;path:string;version:number;extra?:Record<string,unknown>}
