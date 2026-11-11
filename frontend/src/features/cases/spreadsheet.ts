import type ExcelJS from 'exceljs'
import { newIdempotencyKey } from '../../shared/api/idempotency'
import { validateZipBudget } from './zipBudget'

export const fields = [
  '接警编号', '接警类型', '接警单位', '接警分局', '报警内容', '报警地址', '报警人', '报警时间', '报警电话',
  '处警补充结果', '处警反馈时间', '处警修改时间', '发生地址（标准地址）', '简要警情及处理结果',
  '类别', '结果', '涉案物品', '抓获人员', '标签', '备注',
] as const
export type Field = typeof fields[number]
export type LinkedCase = { linked:true; accessible:boolean; id?:string; number?:string; title?:string }
export type CaseInformation = { id: string; version?: number; is_summary?: boolean; can_link_case?:boolean; case_link?:LinkedCase|null } & Partial<Record<Field, string | null>>
const maxRows = 1000

function cellText(cell: ExcelJS.Cell, row: number, field: string): string {
  const value = cell.value
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number') {
    if (field === '接警编号' || field === '报警电话') throw new Error(`第 ${row} 行“${field}”必须为文本格式，以免丢失前导零。`)
    return String(value)
  }
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) throw new Error(`第 ${row} 行“${field}”日期无效。`)
    return value.toISOString().replace('T', ' ').slice(0, 19)
  }
  if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE'
  throw new Error(`第 ${row} 行“${field}”包含公式或不支持的单元格类型，请转换为文本。`)
}

export async function parseWorkbook(buffer: ArrayBuffer, existingNumbers: string[]): Promise<CaseInformation[]> {
  await validateZipBudget(buffer)
  const { default: ExcelJS } = await import('exceljs')
  const workbook = new ExcelJS.Workbook()
  try { await workbook.xlsx.load(buffer) } catch { throw new Error('无法读取 Excel 文件，请选择有效的 .xlsx 文件。') }
  const sheet = workbook.worksheets[0]
  if (!sheet) throw new Error('文件中没有工作表。')
  if (sheet.rowCount > maxRows + 1 || sheet.columnCount > 100) throw new Error('文件最多支持 1000 行数据和 100 列。')
  const headers = new Map<number, Field>()
  const seenHeaders = new Set<string>()
  sheet.getRow(1).eachCell((cell, column) => {
    const name = cellText(cell, 1, '表头').trim()
    if (!name) return
    if (seenHeaders.has(name)) throw new Error(`表头“${name}”重复。`)
    seenHeaders.add(name)
    if (name === '序号' || name === '操作') return
    if (!(fields as readonly string[]).includes(name)) throw new Error(`不认识表头“${name}”，请使用导入模板。`)
    headers.set(column, name as Field)
  })
  if (!seenHeaders.has('接警编号')) throw new Error('缺少“接警编号”表头，请使用导入模板。')
  const numbers = new Set(existingNumbers.map(number => number.trim()).filter(Boolean))
  const imported: CaseInformation[] = []
  let characterCount = 0
  for (let rowNumber = 2; rowNumber <= sheet.rowCount; rowNumber++) {
    const row = sheet.getRow(rowNumber)
    if (!row.hasValues) continue
    row.eachCell((cell, column) => {
      if (headers.has(column)) return
      const title = cellText(sheet.getRow(1).getCell(column), 1, '表头').trim()
      if (title !== '序号' && title !== '操作' && cellText(cell, rowNumber, '未识别列').trim())
        throw new Error(`第 ${rowNumber} 行有未匹配表头的数据，请检查文件。`)
    })
    const record: CaseInformation = { id: newIdempotencyKey() }
    for (const [column, field] of headers) {
      const text = cellText(row.getCell(column), rowNumber, field)
      if (text.length > (field === '接警编号' ? 80 : 10000)) throw new Error(`第 ${rowNumber} 行“${field}”内容过长。`)
      characterCount += text.length
      if (characterCount > 2_000_000) throw new Error('文件内容总长度不能超过 200 万字符。')
      record[field] = text
    }
    const number = record['接警编号']?.trim()
    if (!number) throw new Error(`第 ${rowNumber} 行缺少接警编号。`)
    if (numbers.has(number)) throw new Error(`第 ${rowNumber} 行的接警编号“${number}”重复，未导入任何记录。`)
    record['接警编号'] = number
    numbers.add(number)
    imported.push(record)
  }
  if (!imported.length) throw new Error('文件中没有可导入的数据。')
  return imported
}

export async function createWorkbook(records: CaseInformation[]): Promise<Blob> {
  const { default: ExcelJS } = await import('exceljs')
  const workbook = new ExcelJS.Workbook()
  const sheet = workbook.addWorksheet('接警信息')
  sheet.addRow([...fields])
  sheet.getRow(1).font = { bold: true }
  for (const record of records) sheet.addRow(fields.map(field => record[field] ?? ''))
  sheet.columns.forEach(column => { column.width = 20; column.numFmt = '@' })
  const buffer = await workbook.xlsx.writeBuffer()
  return new Blob([buffer as BlobPart], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}
