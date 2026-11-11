import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import Module from 'node:module'
import path from 'node:path'
const bundle=await build({entryPoints:['src/features/cases/caseInformation.ts'],bundle:true,platform:'node',format:'cjs',external:['exceljs'],write:false})
const compiled=new Module(path.resolve('tests/case-information.bundle.cjs'))
compiled.filename=path.resolve('tests/case-information.bundle.cjs')
compiled.paths=Module._nodeModulePaths(path.resolve('.'))
compiled._compile(bundle.outputFiles[0].text,compiled.filename)
const {loadCaseInformation,toCaseInformationUpdate}=compiled.exports
const fieldNames=['接警编号','接警类型','接警单位','接警分局','报警内容','报警地址','报警人','报警时间','报警电话','处警补充结果','处警反馈时间','处警修改时间','发生地址（标准地址）','简要警情及处理结果','类别','结果','涉案物品','抓获人员','标签','备注']

test('打开详情必须取全量记录，修改可见字段仍保留完整长备注和隐藏字段',async()=>{
 const note='完整备注'.repeat(1000),content='完整报警内容'.repeat(100)
 const full={id:'case-1',version:7,...Object.fromEntries(fieldNames.map(name=>[name,null])),接警编号:'TEST-1',报警内容:content,备注:note,报警电话:'00123'}
 let requested
 const record=await loadCaseInformation(async path=>{requested=path;return structuredClone(full)},'case-1')
 record.结果='已更新'
 const payload=toCaseInformationUpdate(record)
 assert.equal(requested,'/case-information/case-1/detail')
 assert.equal(payload.version,7);assert.equal(payload.fields.备注,note);assert.equal(payload.fields.报警内容,content)
 assert.equal(payload.fields.报警电话,'00123');assert.equal(payload.fields.结果,'已更新')
})

test('摘要以及缺失字段的详情不能生成更新请求，防止用null覆盖未加载字段',async()=>{
 assert.throws(()=>toCaseInformationUpdate({id:'case-1',version:1,is_summary:true,接警编号:'TEST-1'}),/详情未完整加载/)
 assert.throws(()=>toCaseInformationUpdate({id:'case-1',version:1,接警编号:'TEST-1'}),/详情未完整加载/)
 await assert.rejects(loadCaseInformation(async()=>({id:'different',version:1}),'case-1'),/不匹配/)
 await assert.rejects(loadCaseInformation(async()=>({id:'case-1',version:1,is_summary:true}),'case-1'),/详情未完整加载/)
})
