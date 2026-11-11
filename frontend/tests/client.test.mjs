import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import Module from 'node:module'
import path from 'node:path'
const bundle = await build({entryPoints:['src/shared/api/client.ts'],bundle:true,platform:'node',format:'cjs',write:false})
const compiled = new Module(path.resolve('tests/client.bundle.cjs'))
compiled.filename = path.resolve('tests/client.bundle.cjs')
compiled._compile(bundle.outputFiles[0].text,compiled.filename)
const {request,ApiError,isCancelled,createRequestScope}=compiled.exports
const ok=data=>new Response(JSON.stringify(data),{status:200})

test('结构化错误保留请求编号并把导入字段转换为文件行号',async()=>{
 const original=globalThis.fetch
 try{
  globalThis.fetch=async()=>new Response(JSON.stringify({code:'VALIDATION_ERROR',message:'请检查填写的信息',details:[{field:'rows.3.接警编号',code:'INVALID_VALUE',message:'编号过长'}],request_id:'req-123'}),{status:422})
  await assert.rejects(request('/case-information/import','token',{method:'POST'}),error=>{
   assert.ok(error instanceof ApiError);assert.equal(error.code,'VALIDATION_ERROR');assert.equal(error.requestId,'req-123')
   assert.equal(error.details[0].field,'rows.3.接警编号');assert.match(error.message,/Excel 第 5 行/);assert.match(error.message,/req-123/);assert.equal(error.definitive,true);return true
  })
 }finally{globalThis.fetch=original}
})

test('写入超时仍标记结果未知，显式取消与网络失败可区分',async()=>{
 const original=globalThis.fetch
 try{
  globalThis.fetch=async(_url,options)=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}))
  await assert.rejects(request('/cases','token',{method:'POST',timeoutMs:5}),error=>error instanceof ApiError&&!error.definitive&&/超时.*结果尚未确认/.test(error.message))
  const controller=new AbortController();const pending=request('/cases','token',{signal:controller.signal});controller.abort()
  await assert.rejects(pending,isCancelled)
 }finally{globalThis.fetch=original}
})

test('取消后即使传输忽略 abort，旧响应也不能成功返回',async()=>{
 const original=globalThis.fetch;let finish
 try{
  globalThis.fetch=async()=>new Promise(resolve=>finish=resolve)
  const scope=createRequestScope(()=> 'same-token'),pending=scope.api('/cases')
  scope.cancel();finish(ok({items:[{id:'stale'}]}))
  await assert.rejects(pending,isCancelled)
 }finally{globalThis.fetch=original}
})
