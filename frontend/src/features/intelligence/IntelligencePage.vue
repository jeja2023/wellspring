<script setup lang="ts">
import { onMounted } from 'vue'
import { useWorkspace } from '../../app/workspace'
const { intelligence: state, loading } = useWorkspace()
const {clues,total,page,selected,eventPage,people,title,summary,source,reviewNote,objective,assignee,dueDate,transitionNote,result,actorId,activate,show,nextPage,nextEvents,create,review,createTask,transition} = state
const clueStatus: Record<string,string> = { DRAFT:'待核验', REVIEWED:'已核验（开发验证）' }
const taskStatus: Record<string,string> = { OPEN:'待办理', PENDING_REVIEW:'待复核', RETURNED:'已退回', CLOSED:'已关闭' }
const actions: Record<string,string> = {CREATED:'创建草稿', REVIEWED:'人工核验', TASK_CREATED:'创建工单', SUBMIT:'提交核查', RETURN:'退回复核', CLOSE:'复核关闭'}
const results: Record<string,string> = {VERIFIED:'已核实',NO_FINDING:'未发现',INSUFFICIENT:'信息不足',DUPLICATE:'重复线索',TRANSFER:'转其他单位',CONTINUE:'待继续核查'}
const name = (id:string) => people.value.find(p=>p.id===id)?.username ?? '本组织用户'
onMounted(activate)
</script>

<template>
  <div class="title-row"><div><p class="eyebrow">INTELLIGENCE</p><h1>情报线索</h1><p class="muted">线索草稿、人工核验及核查工单。当前仅供虚构数据验证。</p></div></div>
  <div class="warning">开发验证流程：组织内用户可操作，尚未实现正式岗位授权；核验不代表正式事实。跨区碰撞和人、案、物关联尚未实现。</div>
  <div class="two-column">
    <section class="card">
      <h2>线索列表</h2>
      <div class="table-wrap"><table><thead><tr><th>标题</th><th>来源</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="clue in clues" :key="clue.id"><td>{{clue.title}}</td><td>{{clue.source}}</td><td>{{clueStatus[clue.status] || '未知状态'}}</td><td><button class="link" :disabled="loading" @click="show(clue.id)">查看</button></td></tr></tbody></table>
        <p v-if="!clues.length" class="empty">暂无线索</p></div>
      <div class="pagination"><button class="secondary" :disabled="loading || page<=1" @click="nextPage(-1)">上一页</button><span>第 {{page}} 页 · 共 {{total}} 条</span><button class="secondary" :disabled="loading || page*20>=total" @click="nextPage(1)">下一页</button></div>
      <div v-if="selected" class="detail">
        <h2>{{selected.clue.title}}</h2><p><b>来源：</b>{{selected.clue.source}}</p><p><b>摘要：</b>{{selected.clue.summary}}</p><p><b>状态：</b>{{clueStatus[selected.clue.status] || '未知状态'}} · 版本 {{selected.clue.version}}</p>
        <form v-if="selected.clue.status==='DRAFT'" @submit.prevent="review"><h3>人工核验</h3><label>核验说明<input v-model="reviewNote" required maxlength="1000"></label><button :disabled="loading">记录核验</button></form>
        <form v-if="selected.clue.status==='REVIEWED' && !selected.task" @submit.prevent="createTask"><h3>创建核查工单</h3><label>核查目标<textarea v-model="objective" required maxlength="1000"></textarea></label><label>本组织承办人<select v-model="assignee" required><option value="" disabled>选择承办人</option><option v-for="person in people" :key="person.id" :value="person.id">{{person.username}}</option></select></label><label>办理期限（可选）<input v-model="dueDate" type="date"></label><p class="muted">手动填写日期；系统不会自动认定任务完成或生成超期提醒。</p><button :disabled="loading">创建工单</button></form>
        <div v-if="selected.task"><h3>核查工单</h3><p><b>目标：</b>{{selected.task.objective}}</p><p><b>承办人：</b>{{name(selected.task.assignee_id)}}</p><p><b>办理期限：</b>{{selected.task.due_date || '未设置'}}</p><p><b>状态：</b>{{taskStatus[selected.task.status] || '未知状态'}}</p><p v-if="selected.task.result"><b>核查结果：</b>{{results[selected.task.result] || '未知结果'}}</p>
          <form v-if="selected.task.status!=='CLOSED'" @submit.prevent="transition(selected.task.status==='PENDING_REVIEW'?'CLOSE':'SUBMIT')">
            <label v-if="selected.task.status!=='PENDING_REVIEW'">核查结果<select v-model="result"><option v-for="(label,code) in results" :key="code" :value="code">{{label}}</option></select></label>
            <label>处理说明<textarea v-model="transitionNote" required maxlength="1000"></textarea></label>
            <template v-if="selected.task.status==='PENDING_REVIEW'"><p class="muted">需由核查提交人以外的本组织用户复核。</p><button :disabled="loading">复核关闭</button> <button type="button" class="secondary" :disabled="loading || !transitionNote.trim()" @click="transition('RETURN')">退回补充</button></template>
            <template v-else><p v-if="selected.task.assignee_id!==actorId" class="muted">只有承办人可提交核查。</p><button :disabled="loading || selected.task.assignee_id!==actorId">提交核查</button></template>
          </form>
        </div>
        <h3>处理记录</h3><ul><li v-for="event in selected.events.items" :key="event.id">{{actions[event.action] || event.action}} · {{name(event.actor_id)}} · {{event.note}} <span v-if="event.result">· {{results[event.result] || event.result}}</span></li></ul>
        <div class="pagination"><button class="secondary" :disabled="loading || eventPage<=1" @click="nextEvents(-1)">上一页</button><span>第 {{eventPage}} 页 · 共 {{selected.events.total}} 条</span><button class="secondary" :disabled="loading || !selected.events.has_more" @click="nextEvents(1)">下一页</button></div>
      </div>
    </section>
    <section class="card"><h2>新建线索草稿</h2><form @submit.prevent="create"><label>标题<input v-model="title" required maxlength="200"></label><label>来源<input v-model="source" required maxlength="200" placeholder="仅填写虚构来源"></label><label>摘要<textarea v-model="summary" required maxlength="2000" placeholder="仅填写虚构内容"></textarea></label><button :disabled="loading">创建草稿</button></form></section>
  </div>
</template>
