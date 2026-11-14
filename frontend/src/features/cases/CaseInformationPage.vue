<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import { formatTimestamp } from '../../shared/time'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled, RequestCancelled } from '../../shared/api/client'
import { fields, type Field, type CaseInformation, createWorkbook } from './spreadsheet'
import { parseWorkbookInWorker } from './spreadsheetClient'
import { loadCaseInformation, toCaseInformationUpdate } from './caseInformation'
import IntakeCaseDialog from './IntakeCaseDialog.vue'
import ConfirmDialog from '../../shared/components/ConfirmDialog.vue'

const { can, api, command, isAdmin, captureSession, openCase } = useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const records = ref<CaseInformation[]>([])
const transferId = ref('')
const detailOnlyFields: readonly Field[] = ['报警人', '报警电话', '处警反馈时间', '处警修改时间', '简要警情及处理结果', '标签', '备注']
const listFields = fields.filter(field => !detailOnlyFields.includes(field))
const keyword = ref(''), alarmType = ref(''), resultFilter = ref('')
const appliedFilters = ref({ keyword: '', alarm_type: '', result: '' })
const page = ref(1), total = ref(0), pageSize = 20
const alarmTypes = ref<string[]>([]), results = ref<string[]>([])
const typeDistribution = ref<{label: string; count: number}[]>([]), resultDistribution = ref<{label: string; count: number}[]>([])
const loading = ref(false), loadError = ref('')
let loadSequence = 0, summaryLoaded = false
const hasFilters = computed(() => !!(appliedFilters.value.keyword || appliedFilters.value.alarm_type || appliedFilters.value.result))
type Filters = { keyword: string; alarm_type: string; result: string }
type SearchResult = { items: CaseInformation[]; total: number; has_more: boolean; statistics?: { types: {label:string; count:number}[]; results: {label:string; count:number}[] }; options?: { types:string[]; results:string[] } }
async function load(target = 1, filters: Filters = appliedFilters.value, refreshSummary = false) {
  const sequence = ++loadSequence
  const includeSummary = refreshSummary || !summaryLoaded || JSON.stringify(filters) !== JSON.stringify(appliedFilters.value)
  loading.value = true; loadError.value = ''
  try {
    const response: SearchResult = await request('/case-information/search', { method:'POST', body:JSON.stringify({ ...filters, page:target, page_size:pageSize, include_summary:includeSummary, summary_only:true, include_case_links:true }) })
    if (sequence !== loadSequence) return
    records.value = response.items; page.value = target; total.value = response.total; appliedFilters.value = { ...filters }
    if (response.statistics) { typeDistribution.value = response.statistics.types; resultDistribution.value = response.statistics.results }
    if (response.options) { alarmTypes.value = response.options.types; results.value = response.options.results }
    if (includeSummary) summaryLoaded = true
  } catch (error) {
    if (isCancelled(error) || sequence !== loadSequence) return
    loadError.value = error instanceof Error ? error.message : '加载接警信息失败'
  } finally { if (sequence === loadSequence) loading.value = false }
}
const selected = ref<CaseInformation | null>(null)
const draft = ref<CaseInformation | null>(null)
const detailDialog = ref<HTMLDialogElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const spreadsheetBusy = ref(false), spreadsheetError = ref(''), spreadsheetNotice = ref(''), parsing = ref(false)
let parseController: AbortController | undefined
let mounted = true
onBeforeUnmount(() => { mounted = false; parseController?.abort() })
function cancelParsing() { parseController?.abort() }
type DeletedRecord = { id:string; number:string; organization:string; version:number; deleted_at:string }
const deletedDialog = ref<HTMLDialogElement | null>(null), deletedItems = ref<DeletedRecord[]>([])
const deletedPage = ref(1), deletedTotal = ref(0), deletedMore = ref(false), deletedError = ref(''), deletedLoading = ref(false)
async function loadDeleted(target = 1) {
  deletedLoading.value = true; deletedError.value = ''
  try {
    const response = await request('/case-information/admin/deleted', { method:'POST', body:JSON.stringify({page:target,page_size:20}) })
    deletedItems.value = response.items; deletedTotal.value = response.total; deletedMore.value = response.has_more; deletedPage.value = target
  } catch (error) { if (isCancelled(error)) return; deletedItems.value = []; deletedTotal.value = 0; deletedMore.value = false; deletedError.value = error instanceof Error ? error.message : '加载失败' }
  finally { deletedLoading.value = false }
}
async function openDeleted() { deletedDialog.value?.showModal(); await loadDeleted() }
const pendingConfirm = ref<{ title: string; message: string; confirmText: string; danger: boolean; run: () => Promise<void> } | null>(null)
const confirmBusy = ref(false)
const confirmError = ref('')
async function executeConfirm() {
  if (!pendingConfirm.value) return
  confirmBusy.value = true; confirmError.value = ''
  try { await pendingConfirm.value.run(); pendingConfirm.value = null }
  catch (error) { confirmError.value = error instanceof Error ? error.message : '操作失败' }
  finally { confirmBusy.value = false }
}
function restoreRecord(record: DeletedRecord) {
  confirmError.value = ''
  pendingConfirm.value = {
    title: '恢复已隐藏记录',
    message: `确定恢复接警编号“${record.number}”的记录吗？`,
    confirmText: '确认恢复',
    danger: false,
    run: async () => {
      deletedLoading.value = true; deletedError.value = ''
      try {
        await command(`case-information-restore-${record.id}`, `/case-information/admin/${record.id}/restore`, {version:record.version})
        await loadDeleted(deletedPage.value > 1 && deletedItems.value.length === 1 ? deletedPage.value - 1 : deletedPage.value)
        await load(1, appliedFilters.value, true)
      } catch (error) { if (isCancelled(error)) return; deletedError.value = error instanceof Error ? error.message : '恢复失败'; throw error }
      finally { deletedLoading.value = false }
    },
  }
}
const longFields: readonly Field[] = ['报警内容', '处警补充结果', '简要警情及处理结果', '备注']

function display(value: string | null | undefined) {
  return value?.trim() || '—'
}
function search() {
  void load(1, { keyword: keyword.value.trim(), alarm_type: alarmType.value, result: resultFilter.value }, true)
}
function resetFilters() {
  keyword.value = ''; alarmType.value = ''; resultFilter.value = ''
  search()
}
onMounted(() => load())
async function downloadWorkbook(template = false) {
  const current = captureSession()
  spreadsheetBusy.value = true; spreadsheetError.value = ''; spreadsheetNotice.value = ''
  try {
    const exported: CaseInformation[] = template ? [] : (await request('/case-information/export', { method:'POST', body:JSON.stringify({ ...appliedFilters.value }) })).items
    const blob = await createWorkbook(exported)
    if (!current() || !mounted) throw new RequestCancelled()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a'); link.href = url; link.download = template ? '接警信息导入模板.xlsx' : '接警信息-当前筛选结果.xlsx'
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    spreadsheetNotice.value = template ? '模板已生成。' : `已导出当前筛选结果，共 ${exported.length} 条。`
  } catch (error) { if (isCancelled(error)) return; spreadsheetError.value = error instanceof Error ? error.message : '生成 Excel 文件失败，请重试。' }
  finally { spreadsheetBusy.value = false }
}
async function importWorkbook(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const current = captureSession()
  parseController = new AbortController()
  parsing.value = true
  spreadsheetBusy.value = true; spreadsheetError.value = ''; spreadsheetNotice.value = ''
  try {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new Error('请选择 .xlsx 格式的 Excel 文件。')
    if (file.size > 2 * 1024 * 1024) throw new Error('文件不能超过 2 MB。')
    const buffer = await file.arrayBuffer()
    const imported = await parseWorkbookInWorker(buffer, parseController.signal)
    if (!current() || !mounted || parseController.signal.aborted) throw new RequestCancelled()
    parsing.value = false
    const rows = imported.map(record => Object.fromEntries(fields.map(field => [field, record[field] ?? null])))
    await command('case-information-import', '/case-information/import', { rows })
    spreadsheetNotice.value = `已导入 ${imported.length} 条记录；当前筛选条件仍然有效。`
    await load(1, appliedFilters.value, true)
  } catch (error) { if (isCancelled(error)) return; spreadsheetError.value = error instanceof Error ? error.message : '导入失败，请检查文件。' }
  finally { input.value = ''; spreadsheetBusy.value = false; parsing.value = false; parseController = undefined }
}
async function showDetails(record: CaseInformation) {
  spreadsheetBusy.value = true; spreadsheetError.value = ''
  selected.value = null; draft.value = null
  try {
    const full = await loadCaseInformation(request, record.id)
    if (!mounted) return
    selected.value = full
    await nextTick()
    detailDialog.value?.showModal()
  } catch (error) {
    if (!isCancelled(error)) spreadsheetError.value = error instanceof Error ? error.message : '详情加载失败'
  } finally { spreadsheetBusy.value = false }
}
async function saveDetails() {
  if (!draft.value || !selected.value) return
  spreadsheetBusy.value = true; spreadsheetError.value = ''; spreadsheetNotice.value = ''
  try {
    if (draft.value.id !== selected.value.id) throw new Error('编辑记录不匹配，请重新打开详情。')
    const payload = toCaseInformationUpdate(draft.value)
    await command(`case-information-update-${selected.value.id}`, `/case-information/${selected.value.id}/update`, payload)
    detailDialog.value?.close()
    spreadsheetNotice.value = '修改已保存。'
    await load(page.value, appliedFilters.value, true)
  } catch (error) { if (isCancelled(error)) return; spreadsheetError.value = error instanceof Error ? error.message : '保存失败' }
  finally { spreadsheetBusy.value = false }
}
function deleteRecord(record: CaseInformation) {
  confirmError.value = ''
  pendingConfirm.value = {
    title: '隐藏接警记录',
    message: `确定隐藏接警记录“${display(record['接警编号'])}”吗？原记录会保留，案件及来源关联不受影响。`,
    confirmText: '确认隐藏',
    danger: true,
    run: async () => {
      spreadsheetBusy.value = true; spreadsheetError.value = ''; spreadsheetNotice.value = ''
      try {
        await command(`case-information-delete-${record.id}`, `/case-information/${record.id}/delete`, { version: record.version })
        spreadsheetNotice.value = '记录已隐藏。'
        await load(page.value > 1 && records.value.length === 1 ? page.value - 1 : page.value, appliedFilters.value, true)
      } catch (error) { if (isCancelled(error)) return; spreadsheetError.value = error instanceof Error ? error.message : '删除失败'; throw error }
      finally { spreadsheetBusy.value = false }
    },
  }
}
</script>

<template>
  <section class="card case-information" aria-label="接警信息表">
    <div class="case-spreadsheet-actions">
      <button type="button" :disabled="spreadsheetBusy || loading" v-if="can('intake.import')" @click="fileInput?.click()">导入 Excel</button>
      <input ref="fileInput" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden @change="importWorkbook">
      <button type="button" class="secondary" :disabled="spreadsheetBusy || loading" v-if="can('intake.export')" @click="downloadWorkbook(false)">导出当前结果</button>
      <button type="button" class="secondary" :disabled="spreadsheetBusy || loading" @click="downloadWorkbook(true)">下载导入模板</button>
      <button v-if="isAdmin" type="button" class="secondary" :disabled="spreadsheetBusy || loading" @click="openDeleted">已隐藏记录</button>
      <button v-if="parsing" type="button" class="secondary" @click="cancelParsing">取消解析</button>
      <span>支持 .xlsx，最多 1000 行、2 MB；接警编号必填且全系统不能重复。导出最多 1000 条。</span>
    </div>
    <p v-if="spreadsheetError" class="error" role="alert">{{ spreadsheetError }}</p>
    <p v-if="spreadsheetNotice" class="success" role="status">{{ spreadsheetNotice }}</p>
    <p v-if="loadError" class="error" role="alert">列表加载失败：{{ loadError }}。若操作已成功，请重新查询，避免重复提交。</p>
    <form class="case-filters" @submit.prevent="search">
      <label>关键词<input v-model="keyword" type="search" placeholder="搜索全部字段" maxlength="200"></label>
      <label>接警类型<select v-model="alarmType"><option value="">全部类型</option><option v-for="type in alarmTypes" :key="type" :value="type">{{ type }}</option></select></label>
      <label>结果<select v-model="resultFilter"><option value="">全部结果</option><option v-for="result in results" :key="result" :value="result">{{ result }}</option></select></label>
      <div class="case-filter-actions"><button type="submit" :disabled="loading || spreadsheetBusy">查询</button><button type="button" class="secondary" :disabled="loading || spreadsheetBusy" @click="resetFilters">重置</button></div>
    </form>
    <section class="case-dashboard" aria-labelledby="case-dashboard-title">
      <div class="case-dashboard-heading"><h2 id="case-dashboard-title">统计概览</h2><span>按当前查询结果统计</span></div>
      <div class="case-dashboard-grid">
        <div class="case-stat-card case-stat-total"><span>记录总数</span><strong>{{ total }}<small>条</small></strong></div>
        <div v-for="item in typeDistribution" :key="'type-' + item.label" class="case-stat-card"><span>接警类型 · {{ item.label }}</span><strong>{{ item.count }}<small>条</small></strong></div>
        <div v-for="item in resultDistribution" :key="'result-' + item.label" class="case-stat-card"><span>结果 · {{ item.label }}</span><strong>{{ item.count }}<small>条</small></strong></div>
      </div>
    </section>
    <p class="case-filter-count" role="status">{{ loading ? '正在加载…' : `共 ${total} 条记录` }}</p>
    <div class="table-wrap case-information-table" tabindex="0" role="region" aria-label="接警信息列表">
      <table>
        <thead>
          <tr><th scope="col" class="row-number">序号</th><th v-for="field in listFields" :key="field" scope="col">{{ field }}</th><th scope="col">关联案件</th><th scope="col">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="(record, rowIndex) in records" :key="record.id">
            <td class="row-number">{{ (page - 1) * pageSize + rowIndex + 1 }}</td>
            <td v-for="field in listFields" :key="field">{{ display(record[field]) }}</td>
            <td><button v-if="record.case_link?.accessible" type="button" class="link" @click="openCase(record.case_link.number!)">{{record.case_link.number}}</button><span v-else>{{record.case_link?'已关联（当前无案件权限）':'未关联'}}</span></td>
            <td class="case-row-actions"><button type="button" class="link" :disabled="loading || spreadsheetBusy" @click="showDetails(record)">详情</button><button v-if="record.can_link_case&&!record.case_link" type="button" class="link" :disabled="loading||spreadsheetBusy" @click="transferId=record.id">转办 / 关联</button><button type="button" class="link case-delete" :disabled="loading || spreadsheetBusy" v-if="can('intake.hide')" @click="deleteRecord(record)">隐藏</button></td>
          </tr>
          <tr v-if="!records.length && !loading && !loadError"><td :colspan="listFields.length + 3" class="case-information-empty">
            <strong>{{ hasFilters ? '没有符合条件的记录' : '暂无接警信息' }}</strong>
            <span>{{ hasFilters ? '请调整筛选条件后重试。' : '可通过 Excel 导入接警信息。' }}</span>
          </td></tr>
        </tbody>
      </table>
    </div>
    <Pagination :page="page" :total="total" :loading="loading || spreadsheetBusy" @change="load($event)" />
    <dialog ref="deletedDialog" class="case-information-dialog" aria-labelledby="deleted-title">
      <div class="case-detail-heading"><h2 id="deleted-title">已隐藏记录</h2><button type="button" class="link" aria-label="关闭已隐藏记录" @click="deletedDialog?.close()">关闭</button></div>
      <p class="muted">可查看并恢复已隐藏的接警信息。</p>
      <p v-if="deletedError" class="error" role="alert">{{ deletedError }} <button type="button" class="link" @click="loadDeleted(deletedPage)">重试</button></p>
      <p v-if="deletedLoading" role="status">正在处理…</p>
      <div v-else-if="!deletedError" class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>接警编号</th><th>所属组织</th><th>删除时间</th><th>操作</th></tr></thead><tbody><tr v-for="(record, rowIndex) in deletedItems" :key="record.id"><td class="row-number">{{(deletedPage-1)*20+rowIndex+1}}</td><td>{{record.number}}</td><td>{{record.organization}}</td><td>{{formatTimestamp(record.deleted_at)}}</td><td><button type="button" class="link" @click="restoreRecord(record)">恢复</button></td></tr></tbody></table><p v-if="!deletedItems.length" class="empty">暂无已隐藏记录</p></div>
      <Pagination :page="deletedPage" :total="deletedTotal" :loading="deletedLoading" :has-more="deletedMore" @change="loadDeleted($event)" />
    </dialog>
    <dialog ref="detailDialog" class="case-information-dialog" aria-labelledby="case-detail-title" @close="selected = null; draft = null">
      <div class="case-detail-heading">
        <h2 id="case-detail-title">接警信息详情</h2>
        <button type="button" class="link" aria-label="关闭接警信息详情" @click="detailDialog?.close()">关闭</button>
      </div>
      <form v-if="draft" @submit.prevent="saveDetails">
        <div class="case-detail-fields">
          <label v-for="field in fields" :key="field" class="case-detail-field">
            <span>{{ field }}</span>
            <textarea v-if="longFields.includes(field)" v-model="draft[field]" rows="3" maxlength="10000"></textarea>
            <input v-else v-model="draft[field]" :maxlength="field === '接警编号' ? 80 : 10000">
          </label>
        </div>
        <p v-if="spreadsheetError" class="error" role="alert">{{ spreadsheetError }}</p>
        <div class="case-detail-actions"><button type="submit" :disabled="spreadsheetBusy || loading">保存修改</button><button type="button" class="secondary" :disabled="spreadsheetBusy || loading" @click="draft = null">取消编辑</button></div>
      </form>
      <template v-else-if="selected">
      <dl class="case-detail-fields">
        <div v-for="field in fields" :key="field" class="case-detail-field">
          <dt>{{ field }}</dt>
          <dd>{{ display(selected[field]) }}</dd>
        </div>
      </dl>
      <div class="case-detail-actions"><button type="button" v-if="can('intake.write')" @click="draft = { ...selected }">编辑</button><button v-if="selected.can_link_case&&!selected.case_link" type="button" class="secondary" @click="transferId=selected.id;detailDialog?.close()">转办 / 关联</button><button v-if="selected.case_link?.accessible" type="button" class="secondary" @click="openCase(selected.case_link.number!)">查看案件</button></div>
      </template>
    </dialog>
    <IntakeCaseDialog v-if="transferId" :key="transferId" :intake-id="transferId" @close="transferId=''" @saved="load(page,appliedFilters,true)" />
    <ConfirmDialog
      :open="!!pendingConfirm"
      :title="pendingConfirm?.title || '确认操作'"
      :message="pendingConfirm?.message || ''"
      :confirm-text="pendingConfirm?.confirmText"
      :danger="pendingConfirm?.danger"
      :busy="confirmBusy"
      :error="confirmError"
      @close="pendingConfirm = null"
      @confirm="executeConfirm"
    />
  </section>
</template>
