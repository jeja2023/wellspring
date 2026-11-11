import test from 'node:test'
import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { build } from 'esbuild'
import Module from 'node:module'
import path from 'node:path'
import ExcelJS from 'exceljs'

const bundle = await build({ entryPoints: ['src/features/cases/spreadsheet.ts'], bundle: true, platform: 'node', format: 'cjs', external: ['exceljs'], write: false })
const compiled = new Module(path.resolve('tests/case-spreadsheet.bundle.cjs'))
compiled.filename = path.resolve('tests/case-spreadsheet.bundle.cjs')
compiled.paths = Module._nodeModulePaths(path.resolve('.'))
compiled._compile(bundle.outputFiles[0].text, compiled.filename)
const { createWorkbook, parseWorkbook } = compiled.exports
if (!globalThis.crypto) globalThis.crypto = webcrypto

async function sheetBuffer(headers, rows) {
  const workbook = new ExcelJS.Workbook()
  const sheet = workbook.addWorksheet('数据')
  sheet.addRow(headers)
  for (const row of rows) sheet.addRow(row)
  return workbook.xlsx.writeBuffer()
}

test('导出后重新导入保留详情字段、前导零及文本公式', async () => {
  const source = [{ id: 'one', 接警编号: '000001', 报警电话: '012345', 备注: '=测试文本', 结果: '已登记' }]
  const blob = await createWorkbook(source)
  const records = await parseWorkbook(await blob.arrayBuffer(), [])
  assert.equal(records.length, 1)
  assert.equal(records[0]['接警编号'], '000001')
  assert.equal(records[0]['报警电话'], '012345')
  assert.equal(records[0]['备注'], '=测试文本')
})

test('重复编号和缺失编号整批拒绝', async () => {
  const data = await sheetBuffer(['接警编号', '结果'], [['新编号', '已登记'], ['已有编号', '待核查']])
  await assert.rejects(parseWorkbook(data, ['已有编号']), /重复/)
  const missing = await sheetBuffer(['接警编号'], [['']])
  await assert.rejects(parseWorkbook(missing, []), /没有可导入的数据|缺少接警编号/)
})

test('只填写接警编号即可导入，文件内重复编号拒绝整批导入', async () => {
  const sparse = await sheetBuffer(['接警编号', '报警人', '备注'], [['  TEST-01  ', null, null]])
  const records = await parseWorkbook(sparse, [])
  assert.equal(records.length, 1)
  assert.equal(records[0]['接警编号'], 'TEST-01')
  assert.equal(records[0]['报警人'], '')
  assert.equal(records[0]['备注'], '')
  const duplicate = await sheetBuffer(['接警编号'], [['TEST-01'], [' TEST-01 ']])
  await assert.rejects(parseWorkbook(duplicate, []), /重复/)
  const missing = await sheetBuffer(['接警编号', '备注'], [[null, '没有编号']])
  await assert.rejects(parseWorkbook(missing, []), /缺少接警编号/)
})

test('拒绝数字编号、公式以及无表头的数据', async () => {
  const number = await sheetBuffer(['接警编号'], [[123]])
  await assert.rejects(parseWorkbook(number, []), /文本格式/)
  const formula = await sheetBuffer(['接警编号', '备注'], [['A', { formula: '1+1', result: 2 }]])
  await assert.rejects(parseWorkbook(formula, []), /公式/)
  const unlabelled = await sheetBuffer(['接警编号', null], [['A', '意外数据']])
  await assert.rejects(parseWorkbook(unlabelled, []), /未匹配表头/)
})

test('导入不依赖安全上下文限定的 randomUUID', async () => {
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'crypto')
  const data=await sheetBuffer(['接警编号'],[['HTTP-01']])
  try {
    Object.defineProperty(globalThis,'crypto',{configurable:true,value:{getRandomValues:webcrypto.getRandomValues.bind(webcrypto)}})
    const records=await parseWorkbook(data,[])
    assert.match(records[0].id,/^[0-9a-f]{8}-[0-9a-f]{4}-4/)
  } finally {if(descriptor)Object.defineProperty(globalThis,'crypto',descriptor)}
})

test('导入在发送服务端前反馈文件行号和字段长度',async()=>{
  const data=await sheetBuffer(['接警编号'],[['A'.repeat(81)]])
  await assert.rejects(parseWorkbook(data,[]),/第 2 行.*接警编号.*过长/)
})

test('不可信压缩包声明的解压体积在加载 Excel 前被拒绝',async()=>{
  const data=Buffer.from(await sheetBuffer(['接警编号'],[['A']]))
  const central=data.indexOf(Buffer.from([0x50,0x4b,0x01,0x02]))
  assert.ok(central>=0)
  data.writeUInt32LE(9*1024*1024,central+24)
  await assert.rejects(parseWorkbook(data,[]),/解压后内容过大/)
})

test('伪造较小解压声明不能绕过实际流式解压预算',async()=>{
  const {deflateRawSync}=await import('node:zlib')
  const compressed=deflateRawSync(Buffer.alloc(9*1024*1024,65))
  const name=Buffer.from('oversized.xml'),local=Buffer.alloc(30),central=Buffer.alloc(46),end=Buffer.alloc(22)
  local.writeUInt32LE(0x04034b50,0);local.writeUInt16LE(8,8);local.writeUInt32LE(compressed.length,18);local.writeUInt32LE(1,22);local.writeUInt16LE(name.length,26)
  central.writeUInt32LE(0x02014b50,0);central.writeUInt16LE(8,10);central.writeUInt32LE(compressed.length,20);central.writeUInt32LE(1,24);central.writeUInt16LE(name.length,28)
  const offset=local.length+name.length+compressed.length
  end.writeUInt32LE(0x06054b50,0);end.writeUInt16LE(1,8);end.writeUInt16LE(1,10);end.writeUInt32LE(central.length+name.length,12);end.writeUInt32LE(offset,16)
  const data=Buffer.concat([local,name,compressed,central,name,end])
  await assert.rejects(parseWorkbook(data,[]),/实际解压内容过大/)
})
