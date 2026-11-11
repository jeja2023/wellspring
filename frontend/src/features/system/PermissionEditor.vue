<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Pagination from '../../shared/components/Pagination.vue'

type Permission = { code: string; name: string; group: string }
type Role = { id: string; name?: string; code?: string; kind?: string; active: boolean; description?: string; permissions?: string[] }
const props = defineProps<{
  roles: Role[]
  catalog: Permission[]
  reserved: string[]
  role: Role | null
  permissions: string[]
  busy: boolean
  canEdit: boolean
}>()
const emit = defineEmits<{
  select: [id: string]
  change: [permissions: string[]]
  save: []
}>()

const search = ref(''), searchInput = ref(''), activeGroup = ref(''), groupInput = ref(''), selectedOnly = ref(false)
const page = ref(1), pageSize = 20
const pendingRole = ref<string | null>(null)
const selected = computed(() => new Set(props.permissions))
const original = computed(() => new Set(props.role?.permissions || []))
const added = computed(() => props.permissions.filter(code => !original.value.has(code)).length)
const removed = computed(() => [...original.value].filter(code => !selected.value.has(code)).length)
const changes = computed(() => added.value + removed.value)
const selectedCount = computed(() => props.catalog.filter(item => selected.value.has(item.code)).length)
const configurableCount = computed(() => props.catalog.filter(item => !restriction(item)).length)
const groups = computed(() => [...new Set(props.catalog.map(item => item.group))])
const query = computed(() => search.value.trim().toLocaleLowerCase())
const visiblePermissions = computed(() => groups.value.flatMap(group => props.catalog.filter(item => item.group === group &&
  (!activeGroup.value || item.group === activeGroup.value) && (!selectedOnly.value || selected.value.has(item.code)) &&
  (!query.value || `${item.name} ${item.code}`.toLocaleLowerCase().includes(query.value)))))
const visibleCount = computed(() => visiblePermissions.value.length)
const pagePermissions = computed(() => visiblePermissions.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const missingReads = computed(() => [...new Set(props.permissions.filter(code => {
  const resource = code.split('.')[0]
  return resource !== 'system' && resource !== 'audit' && !code.endsWith('.read') && !selected.value.has(`${resource}.read`)
}).map(code => `${code.split('.')[0]}.read`))].map(code => props.catalog.find(item => item.code === code)?.name || code))
const pendingRoleName = computed(() => props.roles.find(role => role.id === pendingRole.value)?.name || '未选择角色')

function restriction(permission: Permission) {
  if (props.reserved.includes(permission.code)) return '仅超级管理员'
  if (props.role?.kind === 'USER' && permission.code.startsWith('system.')) return '需普通管理员角色'
  return ''
}
function selectRole(event: Event) {
  const select = event.target as HTMLSelectElement
  const next = select.value
  select.value = props.role?.id || ''
  if (next === (props.role?.id || '')) return
  if (changes.value) pendingRole.value = next
  else emit('select', next)
}
function confirmSwitch() {
  if (pendingRole.value === null) return
  emit('select', pendingRole.value)
  pendingRole.value = null
}
function toggle(permission: Permission, event: Event) {
  if (props.busy || !props.canEdit || !props.role || restriction(permission)) return
  const next = new Set(props.permissions)
  if ((event.target as HTMLInputElement).checked) next.add(permission.code)
  else next.delete(permission.code)
  emit('change', [...next])
}
function discard() {
  emit('change', [...(props.role?.permissions || [])])
  pendingRole.value = null
}
function applyFilters() { search.value = searchInput.value; activeGroup.value = groupInput.value; page.value = 1 }
function resetFilters() { search.value = ''; searchInput.value = ''; activeGroup.value = ''; groupInput.value = ''; selectedOnly.value = false; page.value = 1 }
watch(() => props.role?.id, () => { resetFilters(); pendingRole.value = null })
watch(changes, value => { if (!value) pendingRole.value = null })
watch(selectedOnly, () => { page.value = 1 })
watch(visibleCount, value => { page.value = Math.min(page.value, Math.max(1, Math.ceil(value / pageSize))) })
</script>

<template>
  <section class="card permission-workspace" :aria-busy="busy" aria-label="角色权限配置">
    <form class="system-search permission-filters" @submit.prevent="applyFilters">
      <label class="permission-role-select">选择授权角色
        <select :value="role?.id || ''" :disabled="busy" @change="selectRole">
          <option value="">选择已有角色</option>
          <option v-for="item in roles" :key="item.id" :value="item.id">{{item.name}}（{{item.kind==='ADMIN'?'普通管理员':'普通用户'}}）{{item.active?'':' · 已停用'}}</option>
        </select>
      </label>
      <label class="permission-search">搜索权限<input v-model="searchInput" type="search" :disabled="!role||busy" placeholder="输入权限名称或代码"></label>
      <label class="permission-module-select">业务模块<select v-model="groupInput" :disabled="!role||busy"><option value="">全部模块</option><option v-for="group in groups" :key="group" :value="group">{{group}}</option></select></label>
      <label class="check-label permission-selected-filter"><input v-model="selectedOnly" type="checkbox" :disabled="!role||busy">仅看已选</label>
      <div class="permission-filter-actions"><button :disabled="!role||busy">查询</button><button type="button" class="secondary" :disabled="!role||busy" @click="resetFilters">重置</button></div>
    </form>
    <div v-if="pendingRole!==null" class="warning permission-switch-note" role="alert">
      <p>当前角色有 {{changes}} 项未保存更改。切换至“{{pendingRoleName}}”将放弃这些更改。</p>
      <div class="actions"><button type="button" class="secondary" @click="pendingRole=null">继续编辑</button><button type="button" @click="confirmSwitch">放弃并切换</button></div>
    </div>
    <dl v-if="role" class="permission-role-summary" aria-label="当前授权角色">
      <div><dt>当前角色</dt><dd>{{role.name}}</dd></div><div><dt>角色级别</dt><dd>{{role.kind==='ADMIN'?'普通管理员':'普通用户'}}</dd></div><div><dt>状态</dt><dd><span class="tag">{{role.active?'启用':'停用'}}</span></dd></div>
    </dl>
    <p class="muted permission-guidance">办理、导入等操作需同时勾选对应查询权限；超级管理员专属权限不可分配给普通角色。保存后，受影响账号需重新登录。</p>
    <p v-if="role" class="muted permission-results-line">共 {{visibleCount}} 项权限；当前角色已选 {{selectedCount}} 项，可配置 {{configurableCount}} 项。</p>
    <div class="table-wrap">
      <table class="permission-table" aria-label="权限目录">
        <thead><tr><th scope="col" class="row-number">序号</th><th scope="col">业务模块</th><th scope="col">权限名称</th><th scope="col">权限代码</th><th scope="col">配置范围</th><th scope="col">授权状态</th></tr></thead>
        <tbody>
          <tr v-for="(permission,index) in role ? pagePermissions : []" :key="permission.code">
            <td class="row-number">{{(page-1)*pageSize+index+1}}</td><td>{{permission.group}}</td><td>{{permission.name}}</td><td>{{permission.code}}</td><td class="muted">{{restriction(permission)||'可配置'}}</td>
            <td><label class="check-label permission-option"><input type="checkbox" :aria-label="permission.name+' '+permission.code" :checked="selected.has(permission.code)" :disabled="busy||!canEdit||!!restriction(permission)" @change="toggle(permission,$event)"><span>{{selected.has(permission.code)?'已授权':'未授权'}}</span></label></td>
          </tr>
          <tr v-if="!role||!visibleCount"><td colspan="6" class="empty permission-empty"><template v-if="!role">尚未选择授权角色</template><template v-else>没有符合条件的权限 <button type="button" class="link" @click="resetFilters">显示全部权限</button></template></td></tr>
        </tbody>
      </table>
    </div>
    <Pagination v-if="role" :page="page" :total="visibleCount" :page-size="pageSize" :loading="busy" @change="page=$event" />
    <div class="permission-save-bar">
      <div class="muted permission-save-summary" aria-live="polite"><span v-if="changes">{{changes}} 项权限更改待保存</span><span v-else>{{role?'权限已与当前配置同步':'请选择授权角色'}}</span><span v-if="changes">新增 {{added}} 项，移除 {{removed}} 项</span><p v-if="missingReads.length" class="permission-validation">还需勾选：{{missingReads.join('、')}}</p></div>
      <div class="actions permission-save-actions"><button type="button" class="secondary" :disabled="busy||!changes" @click="discard">撤销更改</button><button type="button" :disabled="busy||!role||!canEdit||!changes||!!missingReads.length" @click="emit('save')">{{busy?'正在处理…':'保存角色权限'}}</button></div>
    </div>
  </section>
</template>
