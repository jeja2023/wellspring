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
