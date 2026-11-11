export type Metric = {key:string;label:string;unit:string;total:number;period_count:number}
export type Distribution = {key:string;label:string;value:number}
export type Overview = {
  generated_at:string;organization:string;timezone:string;date_basis:string
  range:{days:7|30|90;start_date:string;end_date:string}
  metrics:Metric[]
  trend:{dates:string[];series:{key:string;label:string;values:number[]}[]}
  breakdowns:Record<string,Distribution[]>
}
export const colors=['#0e7770','#2c689a','#aa742c','#8065ad','#b15f77','#418a99']
export function linePath(values:number[],maximum:number):string{
  return values.map((value,index)=>`${index?'L':'M'}${44+index*700/Math.max(1,values.length-1)},${210-value*180/Math.max(1,maximum)}`).join(' ')
}
