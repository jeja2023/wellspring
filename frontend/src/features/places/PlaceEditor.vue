<script setup lang="ts">
import {onBeforeUnmount,reactive,ref} from 'vue'
import FormDialog from '../../shared/components/FormDialog.vue'
import {useWorkspace} from '../../app/workspace'
import {isCancelled} from '../../shared/api/client'
import {kinds,type Place,type PlaceFields} from './types'
const props=defineProps<{place?:Place}>(),emit=defineEmits<{close:[];saved:[row:Place]}>()
const {command,captureSession}=useWorkspace(),busy=ref(false),error=ref('')
const form=reactive<PlaceFields>(props.place?{code:props.place.code,name:props.place.name,kind:props.place.kind,district:props.place.district,address:props.place.address,responsible:props.place.responsible,management_basis:props.place.management_basis,review_on:props.place.review_on}:{code:'',name:'',kind:'APARTMENT',district:'',address:'',responsible:'',management_basis:'',review_on:null})
let alive=true;onBeforeUnmount(()=>{alive=false})
async function save(){busy.value=true;error.value='';const valid=captureSession();try{const row=await command(props.place?'place-edit-'+props.place.id:'place-create',props.place?`/places/${props.place.id}/update`:'/places',{...form,review_on:form.review_on||null,...(props.place?{version:props.place.version}:{})}) as Place;if(alive&&valid())emit('saved',row)}catch(e){if(alive&&!isCancelled(e))error.value=e instanceof Error?e.message:'保存失败'}finally{if(alive)busy.value=false}}
</script>
<template><FormDialog :title="place?'更正场所资料':'新增重点场所'" :wide="true" :busy="busy" :error="error" @close="emit('close')"><form @submit.prevent="save"><div class="place-fields"><label>场所编号<input v-model="form.code" maxlength="80" required></label><label>场所名称<input v-model="form.name" maxlength="200" required></label><label>场所类型<select v-model="form.kind"><option v-for="(name,key) in kinds" :key="key" :value="key">{{name}}</option></select></label><label>所属区域<input v-model="form.district" maxlength="200" required></label><label>责任岗位 / 承办人<input v-model="form.responsible" maxlength="100" required></label><label>下次管理复核日期<input v-model="form.review_on" type="date"></label></div><label>场所地址<input v-model="form.address" maxlength="500" required></label><label>纳入管理依据 / 用途说明<textarea v-model="form.management_basis" maxlength="2000" required></textarea></label><p class="muted">保存后可从业务地图补录坐标；登记场所不产生人员身份或风险结论。</p><button :disabled="busy">{{place?'保存更正':'保存场所'}}</button></form></FormDialog></template>
