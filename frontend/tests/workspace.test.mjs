import test from 'node:test'
import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { build } from 'esbuild'
import Module from 'node:module'
import path from 'node:path'

const bundle = await build({ entryPoints: ['src/app/workspace.ts'], bundle: true, platform: 'node', format: 'cjs', write: false })
const compiled = new Module(path.resolve('tests/workspace.bundle.cjs'))
compiled.filename = path.resolve('tests/workspace.bundle.cjs')
compiled.paths = Module._nodeModulePaths(path.resolve('.'))
compiled._compile(bundle.outputFiles[0].text, compiled.filename)
const { createWorkspace } = compiled.exports
if (!globalThis.crypto) globalThis.crypto = webcrypto

const ok = data => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })

test('成功写入后刷新失败时保留成功提示，防止误认为写入失败', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async (_url, options) => {
      if (options?.method === 'POST') return ok({ id: 'case-1' })
      throw new Error('network unavailable')
    }
    const state = createWorkspace()
    state.caseNumber.value = 'CASE-1'
    state.caseTitle.value = '虚构案件'
    await state.makeCase()
    assert.equal(state.notice.value, '案件草稿已创建')
    assert.match(state.error.value, /操作已成功.*避免重复提交/)
    assert.equal(state.caseNumber.value, '')
  } finally { globalThis.fetch = original }
})

test('响应丢失后同一请求复用幂等键，不允许换对象重发', async () => {
  const original = globalThis.fetch
  const calls = []
  try {
    globalThis.fetch = async (url, options) => {
      if (String(url).includes('/clues/search')) return ok({items:[],total:0,has_more:false})
      if (options?.method === 'POST') {
        calls.push({ url, key: new Headers(options.headers).get('Idempotency-Key') })
        if (calls.length === 1) throw new Error('network unavailable')
        return ok({ id: 'sample-1' })
      }
      return ok({ items: [], total: 0, page: 1, page_size: 20, has_more: false })
    }
    const state = createWorkspace()
    state.evidence.value = [
      { id: 'first', case_id: 'c', parent_id: null, label: '原物一', balance: '10', version: 1 },
      { id: 'second', case_id: 'c', parent_id: null, label: '原物二', balance: '10', version: 1 },
    ]
    state.selected.value = 'first'
    state.sampleLabel.value = '样品'
    state.sampleWeight.value = '1'
    state.sampleReason.value = '测试'
    await state.makeSample()
    assert.match(state.error.value, /结果尚未确认/)
    state.selected.value = 'second'
    await state.makeSample()
    assert.match(state.error.value, /恢复原输入/)
    assert.equal(calls.length, 1)
    state.selected.value = 'first'
    await state.makeSample()
    assert.equal(calls.length, 2)
    assert.equal(calls[0].url, calls[1].url)
    assert.equal(calls[0].key, calls[1].key)
    assert.equal(state.notice.value, '分样流水已记录')
  } finally { globalThis.fetch = original }
})


test('退出后清理上一个用户的筛选、草稿与结果', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => ok({ ok: true })
    const state = createWorkspace()
    state.token.value = 'example'
    state.username.value = 'demo'
    state.caseNumber.value = '未提交草稿'
    state.search.value = '筛选值'
    state.caseTotal.value = 7
    state.page.value = '案件管理'
    await state.logout()
    assert.equal(state.token.value, '')
    assert.equal(state.username.value, '')
    assert.equal(state.caseNumber.value, '')
    assert.equal(state.search.value, '')
    assert.equal(state.caseTotal.value, 0)
    assert.equal(state.page.value, '工作台')
  } finally { globalThis.fetch = original }
})


test('办理期限随工单提交，工作台只显示接口返回的个人工单', async () => {
  const original = globalThis.fetch
  const requests = []
  try {
    globalThis.fetch = async (url, options) => {
      requests.push({url, options})
      if (String(url).includes('/clues/search')) return ok({items:[],total:0,has_more:false})
      if (options?.method === 'POST') return ok({id:'task-1'})
      if (String(url).includes('/tasks/mine')) return ok({items:[{id:'task-1',clue_title:'虚构线索',status:'OPEN',due_date:'2026-11-02'}],total:1,has_more:false})
      if (String(url).includes('/detail')) return ok({clue:{id:'clue-1',status:'REVIEWED',version:3},task:{id:'task-1'},events:{items:[],total:0,has_more:false}})
      return ok({items:[],total:0,has_more:false})
    }
    const state = createWorkspace()
    state.intelligence.selected.value = {clue:{id:'clue-1',title:'虚构',summary:'虚构',source:'虚构',status:'REVIEWED',version:2},task:null,events:{items:[],total:0,has_more:false}}
    state.intelligence.objective.value = '测试'
    state.intelligence.assignee.value = 'person-1'
    state.intelligence.dueDate.value = '2026-11-02'
    await state.intelligence.createTask()
    const posted = requests.find(x=>x.options?.method === 'POST')
    assert.equal(JSON.parse(posted.options.body).due_date, '2026-11-02')
    assert.equal(state.intelligence.dueDate.value, '')
    await state.intelligence.loadMine()
    assert.equal(state.intelligence.myTotal.value, 1)
    assert.equal(state.intelligence.myTasks.value[0].due_date, '2026-11-02')
  } finally { globalThis.fetch = original }
})


test('线索案件关联与撤销使用当前版本并刷新结果', async () => {
  const original = globalThis.fetch
  const calls = []
  try {
    globalThis.fetch = async (url, options) => {
      calls.push({url:String(url), method:options?.method, body:options?.body})
      if (String(url).includes('/clues/search')) return ok({items:[],total:0,has_more:false})
      if (options?.method === 'POST') return ok({id:'link-1'})
      if (String(url).includes('/case-links?')) return ok({items:[{id:'link-1',case_number:'D-1',case_title:'虚构',basis:'依据',status:'ACTIVE',version:1,revoke_reason:null}],total:1,has_more:false})
      if (String(url).includes('/detail?')) return ok({clue:{id:'clue-1',status:'REVIEWED',version:3},task:null,events:{items:[],total:0,has_more:false}})
      return ok({items:[],total:0,has_more:false})
    }
    const state=createWorkspace()
    state.intelligence.selected.value={clue:{id:'clue-1',title:'虚构',summary:'虚构',source:'虚构',status:'REVIEWED',version:2},task:null,events:{items:[],total:0,has_more:false}}
    state.intelligence.caseId.value='case-1'
    state.intelligence.linkBasis.value='依据'
    await state.intelligence.createCaseLink()
    const created=calls.find(c=>c.method==='POST')
    assert.equal(created.url,'/api/intelligence/clues/clue-1/case-links')
    assert.deepEqual(JSON.parse(created.body),{case_id:'case-1',clue_version:2,basis:'依据'})
    assert.equal(state.intelligence.caseLinks.value.length,1)
    state.intelligence.revokeReason.value='关联有误'
    await state.intelligence.revokeCaseLink(state.intelligence.caseLinks.value[0])
    const revoked=calls.find(c=>c.url==='/api/intelligence/case-links/link-1/revoke')
    assert.equal(revoked.url,'/api/intelligence/case-links/link-1/revoke')
    assert.deepEqual(JSON.parse(revoked.body),{version:1,reason:'关联有误'})
    assert.match(state.notice.value,/撤销/)
  } finally {globalThis.fetch=original}
})


test('工单重分派响应丢失后保留输入并以同一幂等键重试', async () => {
  const original = globalThis.fetch
  const writes = []
  try {
    globalThis.fetch = async (url, options) => {
      if (String(url).includes('/clues/search')) return ok({items:[],total:0,has_more:false})
      if (options?.method === 'POST') {
        writes.push({url:String(url),body:options.body,key:new Headers(options.headers).get('Idempotency-Key')})
        if (writes.length === 1) throw new Error('network unavailable')
        return ok({id:'task-1',assignee_id:'person-2',version:2})
      }
      if (String(url).includes('/detail?')) return ok({clue:{id:'clue-1',status:'REVIEWED',version:2},task:{id:'task-1',assignee_id:'person-2',status:'OPEN',version:2},events:{items:[],total:0,has_more:false}})
      return ok({items:[],total:0,has_more:false})
    }
    const state=createWorkspace()
    state.intelligence.selected.value={clue:{id:'clue-1',title:'虚构',summary:'虚构',source:'虚构',status:'REVIEWED',version:2},task:{id:'task-1',objective:'核查',assignee_id:'person-1',due_date:null,status:'OPEN',result:null,version:1},events:{items:[],total:0,has_more:false}}
    state.intelligence.reassigning.value=true
    state.intelligence.reassignee.value='person-2'
    state.intelligence.reassignReason.value='虚构交接'
    await state.intelligence.reassignTask()
    assert.match(state.error.value,/结果尚未确认/)
    assert.equal(state.intelligence.reassignReason.value,'虚构交接')
    await state.intelligence.reassignTask()
    assert.deepEqual(JSON.parse(writes[0].body),{version:1,assignee_id:'person-2',reason:'虚构交接'})
    assert.equal(writes[0].url,'/api/intelligence/tasks/task-1/reassign')
    assert.equal(writes[0].key,writes[1].key)
    assert.equal(state.notice.value,'工单已重新分派')
    assert.equal(state.intelligence.reassigning.value,false)
  } finally { globalThis.fetch=original }
})


test('线索筛选提交后分页使用已应用条件，失败保留结果并可重试', async () => {
  const original = globalThis.fetch
  const bodies = []
  let fail = false
  try {
    globalThis.fetch = async (url, options) => {
      if (String(url).includes('/clues/search')) {
        bodies.push(JSON.parse(options.body))
        if (fail) throw new Error('network')
        return ok({items:[{id:'1',title:'示例'}],total:2,has_more:true})
      }
      return ok([])
    }
    const state=createWorkspace().intelligence
    state.searchInput.value='  测试  '
    state.statusInput.value='DRAFT'
    await state.searchClues()
    assert.deepEqual(bodies[0],{keyword:'测试',status:'DRAFT',page:1,page_size:20})
    state.searchInput.value='尚未查询'
    await state.nextPage(1)
    assert.equal(bodies[1].keyword,'测试')
    assert.equal(bodies[1].page,2)
    fail=true
    await state.searchClues()
    assert.equal(state.page.value,2)
    assert.equal(state.appliedSearch.value,'测试')
    assert.equal(state.clues.value.length,1)
    fail=false
    await state.resetClueSearch()
    assert.equal(state.page.value,1)
    assert.equal(state.searchInput.value,'')
    assert.equal(state.appliedStatus.value,'')
  } finally {globalThis.fetch=original}
})


test('盘点提交使用证物版本，成功后显示余额不变', async () => {
  const original=globalThis.fetch; const writes=[]
  try {
    globalThis.fetch=async (url,options)=>{
      if(options?.method==='POST'){ writes.push({url:String(url),body:JSON.parse(options.body)}); return ok({id:'obs'}) }
      return ok({items:[],total:0,page:1,page_size:20,has_more:false})
    }
    const state=createWorkspace()
    state.selected.value='e1'
    state.evidence.value=[{id:'e1',case_id:'c',parent_id:null,label:'证物',balance:'83',version:2}]
    state.inventory.observedWeight.value='82.9';state.inventory.note.value='测试盘点'
    await state.inventory.submit()
    assert.equal(writes[0].url,'/api/evidence/e1/inventory-observations')
    assert.deepEqual(writes[0].body,{evidence_version:2,observed_weight:'82.9',note:'测试盘点'})
    assert.match(state.notice.value,/余额未改变/)
  } finally {globalThis.fetch=original}
})


test('创建人员只生成未核验草稿并在退出时清理', async () => {
  const original=globalThis.fetch;const calls=[]
  try {
    globalThis.fetch=async (url,options)=>{calls.push({url:String(url),options});if(String(url).includes('/person-drafts/search'))return ok({items:[],total:0,has_more:false});if(options?.method==='POST')return ok({id:'p',verification_status:'UNVERIFIED'});return ok({items:[],total:0,has_more:false})}
    const state=createWorkspace();state.persons.name.value='虚构姓名';state.persons.source.value='虚构来源'
    await state.persons.create()
    assert.deepEqual(JSON.parse(calls[0].options.body),{name:'虚构姓名',source:'虚构来源'})
    assert.match(state.notice.value,/尚未核验/)
    state.persons.name.value='草稿';await state.logout();assert.equal(state.persons.name.value,'')
  } finally {globalThis.fetch=original}
})


test('人员筛选仅在查询成功后切换已应用条件', async () => {
  const original=globalThis.fetch;const bodies=[];let fail=false
  try {
    globalThis.fetch=async (_url,options)=>{bodies.push(JSON.parse(options.body));if(fail)throw new Error('network');return ok({items:[{id:'p',name:'虚构',source:'来源',verification_status:'UNVERIFIED'}],total:1,has_more:false})}
    const state=createWorkspace().persons;state.searchInput.value=' 虚构 ';await state.search()
    assert.deepEqual(bodies[0],{keyword:'虚构',page:1,page_size:20})
    fail=true;state.searchInput.value='新条件';await state.search();assert.equal(state.appliedSearch.value,'虚构');assert.equal(state.people.value.length,1)
    fail=false;await state.clearSearch();assert.equal(state.appliedSearch.value,'');assert.equal(state.searchInput.value,'')
  } finally {globalThis.fetch=original}
})


test('待复核请求失败不会显示陈旧结果，退出清理队列', async () => {
  const original=globalThis.fetch;let fail=false
  try {
    globalThis.fetch=async ()=>{if(fail) throw new Error('network');return ok({items:[{id:'t',clue_id:'c',clue_title:'虚构',status:'PENDING_REVIEW'}],total:1,has_more:false})}
    const workspace=createWorkspace();await workspace.intelligence.loadReviewQueue()
    assert.equal(workspace.intelligence.reviewTotal.value,1)
    fail=true;await workspace.intelligence.loadReviewQueue()
    assert.equal(workspace.intelligence.reviewTotal.value,0);assert.match(workspace.intelligence.reviewError.value,/失败/)
    workspace.intelligence.reset();assert.equal(workspace.intelligence.reviewError.value,'')
  } finally {globalThis.fetch=original}
})


test('盘点差异调查重试和复核提示不会声称余额调整', async () => {
  const original=globalThis.fetch;const writes=[]
  try {
    globalThis.fetch=async (url,options)=>{
      if(options?.method==='POST'){writes.push({url:String(url),body:JSON.parse(options.body),key:new Headers(options.headers).get('Idempotency-Key')});return ok({id:'i',status:'OPEN',version:1})}
      if(String(url).includes('/investigation?'))return ok({investigation:{id:'i',observation_id:'o',status:'OPEN',investigator_id:'u',last_submitter_id:null,version:1},events:{items:[],total:0,has_more:false}})
      return ok({items:[],total:0,has_more:false})
    }
    const workspace=createWorkspace();workspace.inventory.selectedObservation.value={id:'o',book_weight:'83',observed_weight:'82.9',difference:'-0.1',note:'盘点',actor_id:'u',evidence_version:1,created_at:'2026-10-29T00:00:00Z'}
    workspace.inventory.investigationNote.value='调查启动';await workspace.inventory.startInvestigation()
    assert.equal(writes[0].url,'/api/evidence/inventory-observations/o/investigation')
    assert.match(workspace.notice.value,/余额未改变/)
    workspace.inventory.investigationNote.value='调查说明';await workspace.inventory.transitionInvestigation('SUBMIT')
    assert.deepEqual(writes[1].body,{version:1,action:'SUBMIT',note:'调查说明'})
    assert.match(workspace.notice.value,/未调整账面余额/)
  } finally {globalThis.fetch=original}
})
