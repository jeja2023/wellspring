import type { ApiRequest } from '../../shared/api/client'
import { fields, type CaseInformation } from './spreadsheet'

function assertFullRecord(record: CaseInformation) {
  if (record.is_summary || !Number.isInteger(record.version) || (record.version ?? 0) < 1 || fields.some(field => !Object.prototype.hasOwnProperty.call(record, field))) {
    throw new Error('详情未完整加载，请重新打开详情后再编辑。')
  }
}
export async function loadCaseInformation(api: ApiRequest, id: string): Promise<CaseInformation> {
  const record = await api<CaseInformation>(`/case-information/${encodeURIComponent(id)}/detail`)
  if (record.id !== id) throw new Error('详情记录不匹配，请重新查询。')
  assertFullRecord(record)
  return record
}
export function toCaseInformationUpdate(record: CaseInformation) {
  assertFullRecord(record)
  return { version: record.version!, fields: Object.fromEntries(fields.map(field => [field, record[field] ?? null])) }
}
