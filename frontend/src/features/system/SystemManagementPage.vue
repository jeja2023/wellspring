<script setup lang="ts">
import Pagination from '../../shared/components/Pagination.vue'
import { onBeforeUnmount,onMounted,reactive,ref,watch } from 'vue'
import { useWorkspace } from '../../app/workspace'
import { createLatestRequests,isCancelled,RequestCancelled } from '../../shared/api/client'
import './system.css'
import FormDialog from '../../shared/components/FormDialog.vue'
import PermissionEditor from './PermissionEditor.vue'
const editorOpen=ref(false)
type Area='users'|'roles'|'permissions'|'organizations'
type Row={id:string;version:number;name?:string;username?:string;code?:string;kind?:string;active:boolean;org_id?:string;organization?:string;role_id?:string|null;role_name?:string;is_admin?:boolean;parent_id?:string|null;description?:string;permissions?:string[]}
type Permission={code:string;name:string;group:string}
const props=defineProps<{area:Area}>()
const {api,command,captureSession,isAdmin}=useWorkspace(),requests=createLatestRequests(api)
let mounted=true
onBeforeUnmount(()=>{mounted=false;requests.dispose()})
const rows=ref<Row[]>([]),roles=ref<Row[]>([]),organizations=ref<Row[]>([]),catalog=ref<Permission[]>([]),reserved=ref<string[]>([])
const page=ref(1),total=ref(0),keyword=ref(''),applied=ref(''),busy=ref(false),error=ref(''),notice=ref(''),editing=ref<Row|null>(null)
const form=reactive({username:'',password:'',org_id:'',role_id:'',is_admin:false,active:true,code:'',name:'',kind:'USER',description:'',permissions:[] as string[],parent_id:''})
const resetUser=ref<Row|null>(null),resetPassword=ref('')
function ensure(valid:()=>boolean){if(!mounted||!valid())throw new RequestCancelled()}
async function act(fn:(check:()=>void)=>Promise<void>){const valid=captureSession();busy.value=true;error.value='';try{await fn(()=>ensure(valid))}catch(e){if(mounted&&valid()&&!isCancelled(e))error.value=e instanceof Error?e.message:'操作失败'}finally{busy.value=false}}
function clear(){editing.value=null;Object.assign(form,{username:'',password:'',org_id:'',role_id:'',is_admin:false,active:true,code:'',name:'',kind:'USER',description:'',permissions:[],parent_id:''})}
function edit(row:Row){error.value='';editorOpen.value=props.area!=='permissions';clear();editing.value=row;Object.assign(form,{...row,password:'',role_id:row.role_id||'',parent_id:row.parent_id||'',permissions:[...(row.permissions||[])]})}
async function load(target=1,term=applied.value){const valid=captureSession();const area=props.area==='permissions'?'roles':props.area;const response=await requests.latest<{items:Row[];total:number}>('list',`/system/${area}/search`,{method:'POST',body:JSON.stringify({keyword:term,page:target,page_size:20})});ensure(valid);rows.value=response.items;total.value=response.total;page.value=target;applied.value=term}
async function options(){const valid=captureSession();const [a,b]=await Promise.all([api<{roles:Row[];organizations:Row[]}>('/system/options'),api<{items:Permission[];super_only:string[]}>('/system/catalog')]);ensure(valid);roles.value=a.roles;organizations.value=a.organizations;catalog.value=b.items;reserved.value=b.super_only}
async function activate(){clear();notice.value='';keyword.value='';applied.value='';rows.value=[];await act(async()=>{await options();await load()})}
function choosePermissions(id:string){notice.value='';const row=roles.value.find(row=>row.id===id);if(row)edit(row);else clear()}
function save(){void act(async check=>{
 const row=editing.value,area=props.area==='permissions'?'roles':props.area
 let body:Record<string,unknown>
 if(area==='users')body={org_id:form.org_id,role_id:form.is_admin?null:form.role_id||null,is_admin:form.is_admin,active:form.active,...(!row?{username:form.username,password:form.password}:{version:row.version})}
 else if(area==='roles')body={name:form.name,kind:form.kind,description:form.description,permissions:form.permissions,active:form.active,...(!row?{code:form.code}:{version:row.version})}
 else body={name:form.name,parent_id:form.parent_id||null,active:form.active,...(row?{version:row.version}:{})}
 const saved=await command(`system-${area}-${row?.id||'new'}`,`/system/${area}${row?'/'+row.id+'/update':''}`,body) as Row;check()
 if(props.area==='permissions')edit(saved);else{editorOpen.value=false;clear();}notice.value='已保存；账号或角色授权变化后，受影响账号的旧会话已撤销。'
 try{await Promise.all([load(page.value),options()])}catch(e){if(isCancelled(e))throw e;error.value='保存成功但刷新失败，请重新查询，避免重复提交。'}
})}
function reset(){const row=resetUser.value;if(!row)return;void act(async check=>{await command(`reset-password-${row.id}`,`/system/users/${row.id}/password`,{version:row.version,password:resetPassword.value});check();resetUser.value=null;resetPassword.value='';notice.value='密码已重置，旧会话已撤销。请通过受控方式交付新密码。';await load(page.value)})}
watch(()=>props.area,()=>{void activate()})
watch(()=>form.kind,value=>{if(value==='USER')form.permissions=form.permissions.filter(code=>!code.startsWith('system.'))})
onMounted(()=>{void activate()})
</script>

<template>

 <p v-if="error" class="error" role="alert">{{error}} <button type="button" class="link" :disabled="busy" @click="act(()=>load(page))">重新查询</button></p><p v-if="notice" class="success" role="status">{{notice}}</p><p v-if="busy" role="status">正在处理…</p>
 <template v-if="area==='permissions'">
  <PermissionEditor :roles="roles" :catalog="catalog" :reserved="reserved" :role="editing" :permissions="form.permissions" :busy="busy" :can-edit="isAdmin" @select="choosePermissions" @change="form.permissions=$event;notice=''" @save="save" />
 </template>
 <div v-else class="page-list">
  <section class="card">
   <div class="page-toolbar page-toolbar-actions"><button type="button" :disabled="busy" @click="clear();error='';editorOpen=true">新增{{area==='users'?'用户':area==='roles'?'角色':'组织'}}</button></div>
   <form class="system-search" @submit.prevent="act(()=>load(1,keyword.trim()))"><label>查找{{area==='users'?'账号':area==='roles'?'角色':'组织'}}<input v-model="keyword" maxlength="100"></label><button :disabled="busy">查询</button></form>
   <div class="table-wrap">
    <table :class="{'system-parameters-table':area==='users'||area==='roles'}">
     <thead><tr>
      <th scope="col" class="row-number">序号</th>
      <th scope="col">{{area==='users'?'账号':area==='roles'?'角色名称':'名称'}}</th>
      <template v-if="area==='users'"><th scope="col">所属组织</th><th scope="col">角色</th></template>
      <template v-else-if="area==='roles'"><th scope="col">角色代码</th><th scope="col">角色级别</th></template>
      <th v-else scope="col">上级组织</th>
      <th scope="col">状态</th><th scope="col">操作</th>
     </tr></thead>
     <tbody><tr v-for="(row, rowIndex) in rows" :key="row.id">
      <td class="row-number">{{(page-1)*20+rowIndex+1}}</td>
      <td>{{row.username||row.name}}</td>
      <template v-if="area==='users'"><td>{{row.organization}}</td><td>{{row.role_name}}</td></template>
      <template v-else-if="area==='roles'"><td>{{row.code}}</td><td>{{row.kind==='ADMIN'?'普通管理员':'普通用户'}}</td></template>
      <td v-else>{{organizations.find(item=>item.id===row.parent_id)?.name||'无'}}</td>
      <td>{{row.active?'启用':'停用'}}</td>
      <td><button type="button" class="link" :disabled="busy" @click="edit(row)">编辑</button><button v-if="area==='users'" type="button" class="link" :disabled="busy" @click="resetUser=row;resetPassword=''">重置密码</button></td>
     </tr></tbody>
    </table>
    <p v-if="!rows.length&&!busy" class="empty">暂无记录</p>
   </div>
   <Pagination :page="page" :total="total" :loading="busy" @change="act(()=>load($event))" />
   <FormDialog v-if="resetUser" :title="'重置 '+resetUser.username+' 的密码'" :busy="busy" :error="error" @close="resetUser=null;resetPassword=''">   <form  @submit.prevent="reset"><label>新密码<input v-model="resetPassword" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><p class="muted">不显示旧密码；重置成功后退出该账号全部旧会话。</p><button :disabled="busy">确认重置密码</button></form></FormDialog>
  </section>
  <FormDialog v-if="editorOpen" :title="(editing?'编辑':'新增')+(area==='users'?'用户':area==='roles'?'角色':'组织')" :busy="busy" :error="error" :wide="area==='roles'" @close="editorOpen=false;form.password=''"><form @submit.prevent="save">
   <template v-if="area==='users'"><label>账号<input v-model="form.username" pattern="[A-Za-z0-9_.@\-]+" maxlength="80" :disabled="!!editing" required></label><label v-if="!editing">初始密码<input v-model="form.password" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><label>所属组织<select v-model="form.org_id" required :disabled="busy"><option value="" disabled>选择启用组织</option><option v-for="row in organizations" :key="row.id" :value="row.id" :disabled="!row.active">{{row.name}}{{row.active?'':'（停用）'}}</option></select></label><label v-if="isAdmin" class="check-label"><input v-model="form.is_admin" type="checkbox">超级管理员</label><label v-if="!form.is_admin">分配角色<select v-model="form.role_id" required><option value="" disabled>选择启用角色</option><option v-for="row in roles" :key="row.id" :value="row.id" :disabled="!row.active">{{row.name}}{{row.active?'':'（停用）'}}</option></select></label><p class="muted">停用、调整角色或组织后，旧会话立即撤销。最后一个可登录的超级管理员受保护。</p></template>
   <template v-else-if="area==='roles'"><label>角色代码<input v-model="form.code" pattern="[a-z][a-z0-9_]*" maxlength="80" :disabled="!!editing" required></label><label>角色名称<input v-model="form.name" maxlength="120" required></label><label>角色级别<select v-model="form.kind"><option value="USER">普通用户</option><option value="ADMIN">普通管理员</option></select></label><label>职责说明<textarea v-model="form.description" maxlength="1000"></textarea></label><div class="permission-group"><h3>角色权限</h3><label v-for="permission in catalog.filter(item=>!reserved.includes(item.code))" :key="permission.code" class="check-label"><input v-model="form.permissions" type="checkbox" :value="permission.code" :disabled="busy||(form.kind==='USER'&&permission.code.startsWith('system.'))">{{permission.name}}</label></div><p class="muted">操作权限需同时选择对应查询权限。普通管理员仅可管理本组织的普通账号。</p></template>
   <template v-else><label>组织名称<input v-model="form.name" maxlength="120" required></label><label>上级组织<select v-model="form.parent_id"><option value="">无</option><option v-for="row in organizations.filter(item=>item.id!==editing?.id)" :key="row.id" :value="row.id" :disabled="!row.active">{{row.name}}</option></select></label><p class="muted">组织层级仅表示归属，不自动共享下级数据；有启用直属账号或子组织时不能停用。</p></template>
   <label class="check-label"><input v-model="form.active" type="checkbox">启用</label><div class="actions"><button :disabled="busy">保存{{area==='users'?'用户':area==='roles'?'角色':'组织'}}</button><button v-if="editing" type="button" class="secondary" :disabled="busy" @click="editorOpen=false;form.password=''">取消编辑</button></div>
  </form></FormDialog>
 </div>
</template>
