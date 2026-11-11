export type Area='modeling'|'models'|'tactics'
export const names:Record<Area,string>={modeling:'数据建模',models:'模型管理',tactics:'技战法库'}
export const categories:Record<Area,Record<string,string>>={modeling:{DATASET:'主题数据',ENTITY:'实体建模',RELATION:'关系建模'},models:{COLLISION:'碰撞规则',SCORE:'风险评分',FLOW:'分析流程'},tactics:{CLUE:'线索核查',CASE:'案件研判',COMPREHENSIVE:'综合分析'}}
export const statusNames:Record<string,string>={DRAFT:'草稿',ACTIVE:'已启用',ARCHIVED:'已归档'}
export const initialConfig:Record<string,object>={DATASET:{fields:[{name:'record_count',type:'number',required:true}]},ENTITY:{fields:[{name:'entity_id',type:'text',required:true}]},RELATION:{fields:[{name:'source_id',type:'text',required:true},{name:'target_id',type:'text',required:true}]},COLLISION:{mode:'all',conditions:[{field:'record_count',operator:'gte',value:3}]},SCORE:{rules:[{field:'record_count',operator:'gte',value:3,points:30}]},FLOW:{steps:[{name:'数据校验',description:'检查字段、来源及口径'},{name:'规则分析',description:'应用已验证的业务规则'},{name:'人工复核',description:'核验依据并记录结论'}]}}
export type Asset={id:string;kind:string;code:string;name:string;category:string;description:string;project_id:string|null;model_id:string|null;status:string;version:number;created_at:string;updated_at:string;configuration?:Record<string,unknown>}
export type History={id:string;action:string;note:string;created_at:string;snapshot:Asset}
