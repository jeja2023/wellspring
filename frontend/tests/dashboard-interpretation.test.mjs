import test from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import Module from 'node:module'
import path from 'node:path'
const bundle=await build({entryPoints:['src/features/dashboard/interpretation.ts','src/shared/api/client.ts'],bundle:true,platform:'node',format:'cjs',outdir:'out',write:false})
function load(name){const output=bundle.outputFiles.find(item=>item.path.endsWith('/'+name+'.js')||item.path.endsWith('\\'+name+'.js'));const compiled=new Module(path.resolve('tests/'+name+'.bundle.cjs'));compiled.filename=path.resolve('tests/'+name+'.bundle.cjs');compiled.paths=Module._nodeModulePaths(path.resolve('.'));compiled._compile(output.text,compiled.filename);return compiled.exports}
const {createInterpretation}=load('interpretation')
const service={available:true,model:'synthetic-model',message:'合成服务'}
const run=(status='SUCCEEDED')=>({id:'synthetic-task',mode:'dashboard',status,output_text:status==='SUCCEEDED'?'合成统计解读':'',error_message:''})

test('统计解读只提交当前周期参数，关闭重开保留结果，换周期清除旧解读',async()=>{
 const submitted=[]
 const state=createInterpretation(async(path,options)=>{if(path==='/ai/status')return service;if(path==='/ai/runs'){submitted.push(JSON.parse(options.body));return run('QUEUED')}return run()},()=>()=>true)
 try{
  state.enter(7);await state.check();assert.equal(state.canGenerate.value,false)
  state.consent.value=true;await state.generate()
  assert.deepEqual(submitted,[{mode:'dashboard',days:7,text:'',question:'',consent:true}]);assert.equal(state.active.value.output_text,'合成统计解读')
  state.leave();state.enter(7);await state.refresh();assert.equal(state.active.value.output_text,'合成统计解读');assert.equal(submitted.length,1)
  state.leave();state.enter(90);assert.equal(state.days.value,90);assert.equal(state.active.value,null);assert.equal(state.consent.value,false)
 }finally{state.dispose()}
})

test('提交响应丢失后跨弹窗重试复用幂等键和原周期，不能另建重复任务',async()=>{
 const submissions=[];let fail=true
 const state=createInterpretation(async(path,options)=>{if(path==='/ai/status')return service;if(path==='/ai/runs'){submissions.push({key:options.headers['Idempotency-Key'],body:options.body});if(fail)throw Error('结果尚未确认');return run('QUEUED')}return run()},()=>()=>true)
 try{
  state.enter(7);await state.check();state.consent.value=true;await state.generate();assert.ok(state.pending.value)
  state.leave();state.enter(90);await state.check();assert.equal(state.days.value,7)
  fail=false;state.consent.value=true;await state.generate()
  assert.deepEqual(submissions[0],submissions[1]);assert.equal(state.pending.value,null);assert.equal(state.active.value.status,'SUCCEEDED')
 }finally{state.dispose()}
})

test('取消后迟到的运行状态不能覆盖取消结果，销毁后停止接收输出',async()=>{
 let delayed=false,release
 const state=createInterpretation(async(path)=>{if(path==='/ai/status')return service;if(path==='/ai/runs')return run('QUEUED');if(path.endsWith('/cancel'))return run('CANCELLED');if(delayed)return new Promise(resolve=>release=resolve);return run('RUNNING')},()=>()=>true)
 try{
  state.enter(30);await state.check();state.consent.value=true;await state.generate();assert.equal(state.running.value,true)
  delayed=true;const old=state.refresh();await state.cancel();release(run('RUNNING'));await old;assert.equal(state.active.value.status,'CANCELLED')
  const late=state.refresh();state.dispose();release(run());await late;assert.equal(state.active.value.status,'CANCELLED')
 }finally{state.dispose()}
})
