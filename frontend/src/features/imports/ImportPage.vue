<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import FormDialog from '../../shared/components/FormDialog.vue'
const creating=ref(false)
import { formatTimestamp } from '../../shared/time'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests, isCancelled } from '../../shared/api/client'
type Batch={id:string;source:string;sha256:string;mapping_version:string;status:string;created_at:string}
type Row={id:string;row:number;number:string;title:string;preview_status:string;result_status:string|null;reason:string;case_id:string|null}
type Page<T>={items:T[];total:number;has_more:boolean}
type Detail={batch:Batch;rows:Page<Row>}
const {api,command,captureSession}=useWorkspace()
const pageRequests = createLatestRequests(api)
onBeforeUnmount(() => pageRequests.dispose())
const request = (path: string, options: RequestInit = {}) => pageRequests.latest(path.split('?')[0], path, options)
const selected=ref<File|null>(null),source=ref(''),loading=ref(false),error=ref(''),notice=ref('')
const cancelling=ref(false)
const batches=ref<Batch[]>([]),batchPage=ref(1),batchTotal=ref(0),detail=ref<Detail|null>(null),rowPage=ref(1)
const statusNames:Record<string,string>={PREVIEW:'待确认',COMPLETED:'全部新增',PARTIAL:'部分新增',NO_CHANGE:'未新增',CANCELLED:'已取消',NEW:'拟新增',ERROR:'格式错误',CONFLICT:'冲突',CREATED:'已新增'}
function choose(event:Event){selected.value=(event.target as HTMLInputElement).files?.[0] ?? null;error.value='';notice.value=''}
async function list(target=1){const r:Page<Batch>=await request(`/imports/case-batches?page=${target}&page_size=20`);batches.value=r.items;batchTotal.value=r.total;batchPage.value=target}
async function open(id:string,target=1){if(detail.value?.batch.id!==id)cancelling.value=false;const r:Detail=await request(`/imports/case-batches/${id}?page=${target}&page_size=20`);detail.value=r;rowPage.value=target}
async function act(f:()=>Promise<void>){error.value='';notice.value='';loading.value=true;try{await f()}catch(e){if(isCancelled(e))return;error.value=e instanceof Error?e.message:'操作失败'}finally{loading.value=false}}
async function stage(){const current=captureSession();await act(async()=>{
  const file=selected.value;if(!file)throw new Error('请选择 CSV 文件')
  if(!source.value.trim())throw new Error('请填写来源')
  if(!file.name.toLowerCase().endsWith('.csv'))throw new Error('请选择 UTF-8 CSV 文件')
  if(file.size>100000)throw new Error('文件不能超过 100 KB')
  let content:string
  try{content=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer())}catch{throw new Error('文件不是有效的 UTF-8 编码')}
  if(!current())return
  const batch=await command('case-import-stage','/imports/case-batches',{source:source.value,content}) as Batch
  creating.value=false;notice.value='批次已暂存；尚未导入'
  try{await Promise.all([list(1),open(batch.id,1)])}catch(e){if(isCancelled(e))throw e;error.value='暂存成功，但加载结果失败，请从批次列表重新查看。'}
})}
async function cancelBatch(){const batch=detail.value?.batch;if(!batch)return;await act(async()=>{
  await command('case-import-cancel',`/imports/case-batches/${batch.id}/cancel`,{})
  cancelling.value=false;notice.value='批次已取消，暂存记录保留'
  try{await Promise.all([list(batchPage.value),open(batch.id,rowPage.value)])}catch(e){if(isCancelled(e))throw e;error.value='取消已完成，但刷新失败；请重新查看批次。'}
})}
async function confirm(){const batch=detail.value?.batch;if(!batch)return;await act(async()=>{
  await command('case-import-confirm',`/imports/case-batches/${batch.id}/confirm`,{})
  notice.value='批次已处理；请核对逐行结果'
  try{await Promise.all([list(batchPage.value),open(batch.id,rowPage.value)])}catch(e){if(isCancelled(e))throw e;error.value='处理已完成，但刷新失败；请重新查看批次，避免重复操作。'}
})}
onMounted(()=>act(()=>list()))
</script>
<template>
  <p v-if="error&&!creating" role="alert" class="error">{{error}}</p><p v-if="notice" role="status" class="success">{{notice}}</p>
  <p class="muted">此处通过 CSV 创建“案件管理”中的案件记录。接警 Excel 请到“接警信息”导入；相同编号不会自动建立来源关联。</p>

  <div class="actions"><button type="button" :disabled="loading" @click="error='';creating=true">新建导入批次</button></div><FormDialog v-if="creating" title="暂存 CSV" :busy="loading" :error="error" @close="creating=false"><p>UTF-8 编码，表头依次为“案件编号,案件名称”，最多 1000 行、100 KB。暂存会保存解析结果和来源。</p><label>来源<input v-model="source" maxlength="200" :disabled="loading" placeholder="请输入来源"></label><label>文件<input type="file" accept=".csv,text/csv" :disabled="loading" @change="choose"></label><button :disabled="loading || !selected" @click="stage">{{loading?'正在处理…':'暂存并核对'}}</button></FormDialog>
  <section class="card intro"><h2>我的导入批次</h2><p class="muted">仅当前账号和组织可查看。原始文件不保存；逐行内容保存在开发数据库中。</p><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>来源</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody><tr v-for="(b, rowIndex) in batches" :key="b.id"><td class="row-number">{{(batchPage-1)*20+rowIndex+1}}</td><td>{{b.source}}</td><td>{{statusNames[b.status] || '处理中'}}</td><td>{{formatTimestamp(b.created_at)}}</td><td><button class="link" :disabled="loading" @click="act(()=>open(b.id))">查看</button></td></tr></tbody></table><p v-if="!batches.length" class="empty">暂无批次</p></div><Pagination :page="batchPage" :total="batchTotal" :loading="loading" @change="act(()=>list($event))" /></section>
  <section v-if="detail" class="card intro"><h2>批次核对</h2><p>来源：{{detail.batch.source}} · 状态：{{statusNames[detail.batch.status] || '处理中'}} · 映射：{{detail.batch.mapping_version}}</p><p class="muted">内容摘要（SHA-256）：{{detail.batch.sha256}}</p><p>确认时只创建标记为“拟新增”且仍无同编号的案件记录，其他行不会覆盖已有数据。</p><div v-if="detail.batch.status==='PREVIEW'" class="actions"><button :disabled="loading" @click="confirm">确认创建符合条件的案件</button><button class="secondary" :disabled="loading" @click="cancelling=true">取消批次</button></div><div v-if="cancelling && detail.batch.status==='PREVIEW'" class="warning"><p>取消后不能确认该批次，暂存记录仍会保留。</p><button :disabled="loading" @click="cancelBatch">确认取消批次</button> <button class="secondary" :disabled="loading" @click="cancelling=false">返回</button></div><div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>文件行</th><th>案件编号</th><th>案件名称</th><th>预览</th><th>处理结果</th><th>说明</th></tr></thead><tbody><tr v-for="(r, rowIndex) in detail.rows.items" :key="r.id"><td class="row-number">{{(rowPage-1)*20+rowIndex+1}}</td><td>{{r.row}}</td><td>{{r.number}}</td><td>{{r.title}}</td><td>{{statusNames[r.preview_status] || '未知'}}</td><td>{{r.result_status ? statusNames[r.result_status] : '未处理'}}</td><td>{{r.reason || '—'}}</td></tr></tbody></table></div><Pagination :page="rowPage" :total="detail.rows.total" :loading="loading" :has-more="detail.rows.has_more" @change="act(()=>open(detail!.batch.id,$event))" /></section>
</template>
