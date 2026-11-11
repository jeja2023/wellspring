<script setup lang="ts">
import {ref} from 'vue'
import {useWorkspace} from '../../app/workspace'
import AnalysisWorkspace from './AnalysisWorkspace.vue'
import {names,type Area} from './definitions'
const {can}=useWorkspace()
const tabs=(['modeling','models','tactics'] as Area[]).filter(area=>can(area+'.read'))
const active=ref<Area>(tabs[0]||'modeling')
</script>
<template><div><div class="analysis-tabs" role="tablist" aria-label="分析建模分类"><button v-for="area in tabs" :key="area" type="button" role="tab" :aria-selected="active===area" :class="{secondary:active!==area}" @click="active=area">{{names[area]}}</button></div><AnalysisWorkspace v-if="tabs.length" :key="active" :area="active"/><section v-else class="card empty">当前角色没有分析建模查询权限</section></div></template>
