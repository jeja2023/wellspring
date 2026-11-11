<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import FormDialog from '../../shared/components/FormDialog.vue'

const {can}=useWorkspace()
import { onMounted,ref } from 'vue'
import { useWorkspace } from '../../app/workspace'
const { intelligence: state, loading } = useWorkspace()
const {clues,total,page,searchInput,statusInput,appliedSearch,appliedStatus,searchClues,resetClueSearch,selected,eventPage,people,caseChoices,casePage,caseTotal,caseSearch,caseId,linkBasis,caseLinks,linkPage,linkTotal,revokeId,revokeReason,reassigning,reassignee,reassignReason,reassignTask,searchLinkCases,nextLinkCases,nextLinks,createCaseLink,revokeCaseLink,title,summary,source,reviewNote,objective,assignee,dueDate,transitionNote,result,actorId,activate,show,nextPage,nextEvents,create,review,createTask,transition} = state
const clueStatus: Record<string,string> = { DRAFT:'待核验', REVIEWED:'已核验（开发验证）' }
const taskStatus: Record<string,string> = { OPEN:'待办理', PENDING_REVIEW:'待复核', RETURNED:'已退回', CLOSED:'已关闭' }
const actions: Record<string,string> = {CREATED:'创建草稿', REVIEWED:'人工核验', TASK_CREATED:'创建工单', CASE_LINKED:'关联案件', CASE_LINK_REVOKED:'撤销案件关联', REASSIGN:'重新分派', SUBMIT:'提交核查', RETURN:'退回复核', CLOSE:'复核关闭'}
const results: Record<string,string> = {VERIFIED:'已核实',NO_FINDING:'未发现',INSUFFICIENT:'信息不足',DUPLICATE:'重复线索',TRANSFER:'转其他单位',CONTINUE:'待继续核查'}
const name = (id:string) => people.value.find(p=>p.id===id)?.username ?? '本组织用户'
onMounted(activate)
const {error}=useWorkspace()
const creating=ref(false)
async function submitCreate(){if(await create())creating.value=false}
</script>

<template>

  <div class="page-list">
    <section class="card">
      <div class="page-toolbar page-toolbar-actions"><button v-if="can('intelligence.write')" type="button" :disabled="loading" @click="error='';creating=true">新建线索</button></div>
      <form @submit.prevent="searchClues"><label>标题或来源<input v-model="searchInput" maxlength="100" placeholder="输入标题或来源"></label><label>核验状态<select v-model="statusInput"><option value="">全部状态</option><option value="DRAFT">待核验</option><option value="REVIEWED">已核验（开发验证）</option></select></label><div class="actions"><button :disabled="loading">查询</button><button type="button" class="secondary" :disabled="loading" @click="resetClueSearch">重置</button></div></form>
      <p class="muted">仅在当前组织中按标题或来源筛选；摘要不参与搜索。</p>
      <div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>标题</th><th>来源</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="(clue, rowIndex) in clues" :key="clue.id"><td class="row-number">{{(page-1)*20+rowIndex+1}}</td><td>{{clue.title}}</td><td>{{clue.source}}</td><td>{{clueStatus[clue.status] || '未知状态'}}</td><td><button class="link" :disabled="loading" @click="show(clue.id)">查看</button></td></tr></tbody></table>
        <p v-if="!clues.length" class="empty">{{appliedSearch || appliedStatus ? '没有符合条件的线索' : '暂无线索'}}</p></div>
      <Pagination :page="page" :total="total" :loading="loading" @change="nextPage($event-page)" />
      <div v-if="selected" class="detail">
        <h2>{{selected.clue.title}}</h2><p><b>来源：</b>{{selected.clue.source}}</p><p><b>摘要：</b>{{selected.clue.summary}}</p><p><b>状态：</b>{{clueStatus[selected.clue.status] || '未知状态'}} · 版本 {{selected.clue.version}}</p>
        <form v-if="selected.clue.status==='DRAFT'" v-show="can('intelligence.write')" @submit.prevent="review"><h3>人工核验</h3><label>核验说明<input v-model="reviewNote" required maxlength="1000"></label><button :disabled="loading">记录核验</button></form>
        <form v-if="selected.clue.status==='REVIEWED' && !selected.task" v-show="can('intelligence.write')" @submit.prevent="createTask"><h3>创建核查工单</h3><label>核查目标<textarea v-model="objective" required maxlength="1000"></textarea></label><label>本组织承办人<select v-model="assignee" required><option value="" disabled>选择承办人</option><option v-for="person in people" :key="person.id" :value="person.id">{{person.username}}</option></select></label><label>办理期限（可选）<input v-model="dueDate" type="date"></label><p class="muted">手动填写日期；系统不会自动认定任务完成或生成超期提醒。</p><button :disabled="loading">创建工单</button></form>
        <div v-if="selected.task"><h3>核查工单</h3><p><b>目标：</b>{{selected.task.objective}}</p><p><b>承办人：</b>{{name(selected.task.assignee_id)}}</p><p><b>办理期限：</b>{{selected.task.due_date || '未设置'}}</p><p><b>状态：</b>{{taskStatus[selected.task.status] || '未知状态'}}</p><p v-if="selected.task.result"><b>核查结果：</b>{{results[selected.task.result] || '未知结果'}}</p>
          <div v-if="selected.task.status==='OPEN' || selected.task.status==='RETURNED'">
            <button v-if="!reassigning" type="button" class="secondary" :disabled="loading" @click="reassigning=true">重新分派</button>
            <form v-show="can('intelligence.write')" v-else @submit.prevent="reassignTask"><h4>重新分派工单</h4><p class="muted">仅供本组织开发验证；原承办人将不能继续提交，历史记录保留。</p><label>新承办人<select v-model="reassignee" required><option value="" disabled>选择新承办人</option><option v-for="person in people.filter(p=>p.id!==selected?.task?.assignee_id)" :key="person.id" :value="person.id">{{person.username}}</option></select></label><label>分派原因<textarea v-model="reassignReason" required maxlength="1000"></textarea></label><button :disabled="loading">确认重新分派</button> <button type="button" class="secondary" :disabled="loading" @click="reassigning=false">取消</button></form>
          </div>
          <form v-if="selected.task.status!=='CLOSED'" v-show="can('intelligence.write')" @submit.prevent="transition(selected.task.status==='PENDING_REVIEW'?'CLOSE':'SUBMIT')">
            <label v-if="selected.task.status!=='PENDING_REVIEW'">核查结果<select v-model="result"><option v-for="(label,code) in results" :key="code" :value="code">{{label}}</option></select></label>
            <label>处理说明<textarea v-model="transitionNote" required maxlength="1000"></textarea></label>
            <template v-if="selected.task.status==='PENDING_REVIEW'"><p class="muted">需由核查提交人以外的本组织用户复核。</p><button :disabled="loading">复核关闭</button> <button type="button" class="secondary" :disabled="loading || !transitionNote.trim()" @click="transition('RETURN')">退回补充</button></template>
            <template v-else><p v-if="selected.task.assignee_id!==actorId" class="muted">只有承办人可提交核查。</p><button :disabled="loading || selected.task.assignee_id!==actorId">提交核查</button></template>
          </form>
        </div>
        <h3>关联案件</h3>
        <p class="muted">仅展示当前组织可见的案件关联；撤销仅改变关联，不撤销案件或线索。</p>
        <div class="table-wrap"><table><thead><tr><th scope="col" class="row-number">序号</th><th>案件</th><th>关联依据</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="(link, rowIndex) in caseLinks" :key="link.id"><td class="row-number">{{(linkPage-1)*20+rowIndex+1}}</td><td>{{link.case_number}} · {{link.case_title}}</td><td>{{link.basis}}</td><td>{{link.status==='ACTIVE' ? '有效' : link.status==='REVOKED' ? '已撤销' : '未知状态'}}<span v-if="link.revoke_reason"> · {{link.revoke_reason}}</span></td><td><button v-if="link.status==='ACTIVE'" class="link" :disabled="loading" @click="revokeId=link.id;revokeReason=''">撤销</button><form v-if="revokeId===link.id" v-show="can('intelligence.write')" @submit.prevent="revokeCaseLink(link)"><label>撤销原因<input v-model="revokeReason" required maxlength="1000"></label><p class="muted">将保留关联历史，不改变案件和线索状态。</p><button :disabled="loading">确认撤销关联</button> <button type="button" class="secondary" @click="revokeId=''">取消</button></form></td></tr></tbody></table><p v-if="!caseLinks.length" class="empty">暂无案件关联</p></div>
        <Pagination :page="linkPage" :total="linkTotal" :loading="loading" @change="nextLinks($event-linkPage)" />
        <div v-if="selected.clue.status==='REVIEWED'">
          <form @submit.prevent="searchLinkCases"><label>查找本组织案件<input v-model="caseSearch" maxlength="100" placeholder="输入案件编号或名称"></label><button class="secondary" :disabled="loading">查询案件</button></form>
          <Pagination :page="casePage" :total="caseTotal" :loading="loading" @change="nextLinkCases($event-casePage)" />
          <form v-if="can('intelligence.write')" @submit.prevent="createCaseLink"><label>关联案件<select v-model="caseId" required><option value="" disabled>请先查询并选择案件</option><option v-for="c in caseChoices" :key="c.id" :value="c.id">{{c.number}} · {{c.title}}</option></select></label><label>关联依据<textarea v-model="linkBasis" required maxlength="1000"></textarea></label><button :disabled="loading">记录案件关联</button></form>
        </div>
        <h3>处理记录</h3><ul><li v-for="event in selected.events.items" :key="event.id">{{actions[event.action] || event.action}} · {{name(event.actor_id)}} · {{event.note}} <span v-if="event.action==='REASSIGN' && event.assignee_before_id && event.assignee_after_id">· {{name(event.assignee_before_id)}} → {{name(event.assignee_after_id)}}</span><span v-if="event.result">· {{results[event.result] || event.result}}</span></li></ul>
        <Pagination :page="eventPage" :total="selected.events.total" :loading="loading" :has-more="selected.events.has_more" @change="nextEvents($event-eventPage)" />
      </div>
    </section>
    <FormDialog v-if="creating" title="新建线索草稿" :busy="loading" :error="error" @close="creating=false"><form v-if="can('intelligence.write')" @submit.prevent="submitCreate"><label>标题<input v-model="title" required maxlength="200"></label><label>来源<input v-model="source" required maxlength="200" placeholder="请输入来源"></label><label>摘要<textarea v-model="summary" required maxlength="2000" placeholder="请输入内容"></textarea></label><button :disabled="loading">创建草稿</button></form></FormDialog>
  </div>
</template>
