import test from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import Module from 'node:module'
import path from 'node:path'
const result=await build({entryPoints:['src/features/dashboard/workbench.ts'],bundle:true,platform:'node',format:'cjs',write:false})
const module=new Module(path.resolve('tests/workbench.bundle.cjs'));module.filename=path.resolve('tests/workbench.bundle.cjs');module.paths=Module._nodeModulePaths(path.resolve('.'));module._compile(result.outputFiles[0].text,module.filename)
const {createWorkbench,stateName}=module.exports
const data=(queue='todo',page=1,scope='all')=>({items:[{id:queue+page}],queue,page,module:scope,counts:{todo:26,review:4,overdue:12,due_today:1},total:26,page_size:10,has_more:true})
test('工作台按服务端全量计数及已应用队列翻页，失败保留一致结果并可刷新',async()=>{
  const calls=[];let fail=false
  const state=createWorkbench(async path=>{calls.push(path);if(fail)throw Error('合成断网');const q=new URL('http://test'+path).searchParams;return data(q.get('queue'),Number(q.get('page')),q.get('module'))})
  await state.load(1,'overdue','places');await state.load(2)
  assert.equal(state.data.value.page,2);assert.equal(state.data.value.queue,'overdue');assert.equal(state.data.value.counts.overdue,12)
  fail=true;await state.load(1,'review','persons');assert.equal(state.data.value.page,2);assert.equal(state.data.value.module,'places');assert.match(state.error.value,/断网/)
  fail=false;await state.load();assert.equal(new URL('http://test'+calls.at(-1)).searchParams.get('queue'),'overdue');state.dispose()
})
test('工作台迟到或卸载后的响应不回写，新请求完成前保持loading',async()=>{
  const pending=[];const state=createWorkbench(()=>new Promise(resolve=>pending.push(resolve)))
  const old=state.load(1),latest=state.load(2,'review');pending[0](data());await old;assert.equal(state.loading.value,true)
  pending[1](data('review',2));await latest;assert.equal(state.data.value.page,2)
  const after=state.load(3);state.dispose();pending[2](data('review',3));await after;assert.equal(state.data.value,null)
  assert.equal(stateName({kind:'incident',status:'SUBMITTED'}),'待复核办结')
})
