<script setup lang="ts">
import {computed,ref,watch} from 'vue'
const props=withDefaults(defineProps<{page:number;total:number;pageSize?:number;loading?:boolean;hasMore?:boolean;label?:string}>(),{pageSize:20,loading:false,hasMore:undefined,label:'数据分页'})
const emit=defineEmits<{change:[page:number]}>()
const pages=computed(()=>Math.min(100000,Math.max(1,props.page,Math.ceil(props.total/props.pageSize))))
const numbers=computed(()=>{const start=Math.max(1,Math.min(props.page-2,pages.value-4));return Array.from({length:Math.min(5,pages.value)},(_,index)=>start+index)})
const jump=ref(props.page)
watch(()=>props.page,page=>{jump.value=page})
const canNext=computed(()=>props.hasMore??props.page<pages.value)
function change(page:number){if(!props.loading&&Number.isInteger(page)&&page>=1&&page<=pages.value&&page!==props.page)emit('change',page)}
</script>
<template>
 <nav v-if="total>0" class="pagination" :aria-label="label" :aria-busy="loading">
  <span class="pagination-summary">第 {{page}} 页 · 共 {{total}} 条</span><span class="pagination-size">每页 {{pageSize}} 条</span>
  <div class="pagination-buttons"><button type="button" class="secondary" :disabled="loading||page<=1" @click="change(1)">首页</button><button type="button" class="secondary" :disabled="loading||page<=1" @click="change(page-1)">上一页</button><button v-for="number in numbers" :key="number" type="button" :class="{secondary:number!==page}" :aria-label="'第 '+number+' 页'" :aria-current="number===page?'page':undefined" :disabled="loading||number===page" @click="change(number)">{{number}}</button><button type="button" class="secondary" :disabled="loading||!canNext" @click="change(page+1)">下一页</button><button type="button" class="secondary" :disabled="loading||!canNext" @click="change(pages)">末页</button></div>
  <form v-if="pages>5" class="pagination-jump" @submit.prevent="change(Number(jump))"><label>跳至<input v-model.number="jump" type="number" min="1" :max="pages" step="1" :disabled="loading" required aria-label="目标页码"></label><button type="submit" class="secondary" :disabled="loading">跳转</button></form>
 </nav>
</template>
