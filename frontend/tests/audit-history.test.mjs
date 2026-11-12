import test from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import Module from 'node:module'
import path from 'node:path'
const bundle=await build({entryPoints:['src/features/audit/controller.ts'],bundle:true,platform:'node',format:'cjs',write:false})
const compiled=new Module(path.resolve('tests/audit-history.bundle.cjs'))
compiled.filename=path.resolve('tests/audit-history.bundle.cjs');compiled.paths=Module._nodeModulePaths(path.resolve('.'));compiled._compile(bundle.outputFiles[0].text,compiled.filename)
const {createAuditHistory,AUDIT_PAGE_SIZE}=compiled.exports
const result=id=>({items:[{id,action_name:'创建案件记录'}],total:40,has_more:true})

test('个人审计以15条分页，翻页使用已应用条件，失败保留上一组一致结果',async()=>{
 const calls=[];let fail=false
 const state=createAuditHistory(async path=>{calls.push(path);if(fail)throw Error('合成断网');return result('row')},'mine')
 assert.equal(AUDIT_PAGE_SIZE,15)
 Object.assign(state.filters,{action:' 创建案件 ',object_id:'object-1',start_date:'2026-11-11',end_date:'2026-11-12'})
 await state.search();const query=new URL('https://synthetic.invalid'+calls[0]).searchParams
 assert.equal(query.get('page_size'),'15');assert.equal(query.get('action'),'创建案件');assert.equal(query.get('object_id'),'object-1');assert.equal(query.get('start_date'),'2026-11-11')
 state.filters.action='未提交筛选';await state.load(2)
 assert.equal(new URL('https://synthetic.invalid'+calls.at(-1)).searchParams.get('action'),'创建案件')
 fail=true;await state.search();assert.equal(state.page.value,2);assert.equal(state.applied.value.action,'创建案件');assert.equal(state.items.value[0].id,'row');assert.match(state.error.value,/合成断网/)
 fail=false;await state.reset();assert.equal(state.page.value,1);assert.equal(state.applied.value.action,'');assert.equal(new URL('https://synthetic.invalid'+calls.at(-1)).searchParams.has('start_date'),false)
 state.dispose()
})

test('系统日志提交中文内容和账号条件；迟到查询及销毁后响应不能覆盖新状态',async()=>{
 const resolvers=[];const state=createAuditHistory(async(path,options)=>new Promise(resolve=>resolvers.push({path,body:JSON.parse(options.body),resolve})),'system')
 state.filters.username='合成账号';state.filters.action='登录系统';const first=state.search();state.filters.action='新增用户';const second=state.search()
 assert.equal(resolvers[1].body.page_size,15);assert.equal(resolvers[1].body.username,'合成账号');assert.equal(resolvers[1].body.action,'新增用户')
 resolvers[1].resolve(result('new'));await second;resolvers[0].resolve(result('old'));await first;assert.equal(state.items.value[0].id,'new')
 const pending=state.load(2);state.dispose();resolvers[2].resolve(result('after-dispose'));await pending;assert.equal(state.page.value,1);assert.equal(state.items.value[0].id,'new')
})
