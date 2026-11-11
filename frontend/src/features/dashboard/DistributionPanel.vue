<script setup lang="ts">
import {computed} from 'vue'
import type {Distribution} from './screen'
const props=defineProps<{title:string;items:Distribution[]}>()
const total=computed(()=>props.items.reduce((sum,item)=>sum+item.value,0))
const maximum=computed(()=>Math.max(1,...props.items.map(item=>item.value)))
</script>
<template>
  <section class="card screen-distribution"><h2>{{title}}</h2>
    <p v-if="!total" class="empty">暂无统计数据</p>
    <ul v-else><li v-for="item in items" :key="item.key"><div><span :title="item.label">{{item.label}}</span><strong>{{item.value.toLocaleString('zh-CN')}}</strong></div><div class="screen-bar" aria-hidden="true"><span :style="{width:item.value/maximum*100+'%'}"></span></div></li></ul>
    <p class="muted screen-distribution-total">合计 {{total.toLocaleString('zh-CN')}} 条 · 当前全量</p>
  </section>
</template>
