<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref,watch} from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {useWorkspace} from '../../app/workspace'
import {isCancelled} from '../../shared/api/client'
import {layerColors,layerNames,type GeoResource} from './types'
const props=defineProps<{points:GeoResource[];tiles:boolean;selecting?:boolean}>()
const emit=defineEmits<{select:[point:GeoResource];pick:[longitude:number,latitude:number];coverage:[missing:boolean]}>()
const {api}=useWorkspace(),host=ref<HTMLElement>()
let map:L.Map|undefined,markers:L.LayerGroup|undefined,resize:ResizeObserver|undefined
const pending=new Map<HTMLElement,AbortController>()
let alive=true,loadedTiles=0,failedTiles=0
function grid(canvas:HTMLCanvasElement,coords:L.Coords){
  const ctx=canvas.getContext('2d');if(!ctx)return
  ctx.fillStyle='#eef4f5';ctx.fillRect(0,0,256,256);ctx.strokeStyle='#d8e4e8';ctx.lineWidth=1
  for(let i=0;i<=256;i+=64){ctx.beginPath();ctx.moveTo(i,0);ctx.lineTo(i,256);ctx.moveTo(0,i);ctx.lineTo(256,i);ctx.stroke()}
  const corner=L.CRS.EPSG3857.pointToLatLng(L.point(coords.x*256,coords.y*256),coords.z)
  ctx.fillStyle='#718997';ctx.font='11px sans-serif';ctx.fillText(`${corner.lng.toFixed(3)}°, ${corner.lat.toFixed(3)}°`,8,18)
}
function redraw(){
  if(!map||!markers)return;markers.clearLayers()
  const buckets=new Map<string,GeoResource[]>()
  for(const row of props.points){if(row.longitude===null||row.latitude===null)continue
    const xy=map.latLngToContainerPoint([row.latitude,row.longitude]),key=`${Math.floor(xy.x/36)}:${Math.floor(xy.y/36)}`
    const bucket=buckets.get(key)||[];bucket.push(row);buckets.set(key,bucket)
  }
  for(const rows of buckets.values()){
    const row=rows[0],cluster=rows.length>1
    const icon=L.divIcon({className:'business-point'+(cluster?' business-cluster':''),html:cluster?String(rows.length):`<span style="background:${layerColors[row.resource_type]}"></span>`,iconSize:cluster?[32,32]:[24,24],iconAnchor:cluster?[16,16]:[12,12]})
    const title=cluster?`${rows.length} 个相邻点位`:`${layerNames[row.resource_type]}：${row.name}`
    const marker=L.marker([row.latitude!,row.longitude!],{icon,title,alt:title,keyboard:true}).addTo(markers)
    const tooltip=document.createElement('span');tooltip.textContent=title;marker.bindTooltip(tooltip)
    marker.on('click',()=>{
      if(!cluster){emit('select',row);return}
      const list=document.createElement('div');list.className='map-cluster-list'
      for(const item of rows){const button=document.createElement('button');button.type='button';button.textContent=`${layerNames[item.resource_type]} · ${item.name}`;button.addEventListener('click',()=>{emit('select',item);map?.closePopup()});list.append(button)}
      marker.bindPopup(list,{maxHeight:220}).openPopup()
    })
  }
}
function fit(){if(!map)return;const coords=props.points.filter(row=>row.latitude!==null&&row.longitude!==null).map(row=>L.latLng(row.latitude!,row.longitude!));if(coords.length)map.fitBounds(L.latLngBounds(coords),{padding:[45,45],maxZoom:16})}
function focus(row:GeoResource){if(map&&row.latitude!==null&&row.longitude!==null)map.setView([row.latitude,row.longitude],Math.max(map.getZoom(),16))}
function bounds():[number,number,number,number]|undefined{if(!map)return;const b=map.getBounds();return [Math.max(-180,b.getWest()),Math.max(-85,b.getSouth()),Math.min(180,b.getEast()),Math.min(85,b.getNorth())]}
defineExpose({fit,focus,bounds})
onMounted(()=>{
  map=L.map(host.value!,{zoomControl:false,minZoom:2,maxZoom:20,maxBounds:[[-85,-180],[85,180]],maxBoundsViscosity:1}).setView([35,105],4)
  L.control.zoom({zoomInTitle:'放大',zoomOutTitle:'缩小'}).addTo(map);L.control.scale({imperial:false}).addTo(map)
  map.attributionControl.setPrefix('');map.on('click',(event:L.LeafletMouseEvent)=>{if(props.selecting)emit('pick',Number(event.latlng.lng.toFixed(6)),Number(event.latlng.lat.toFixed(6)))})
  const Tiles=L.GridLayer.extend({createTile(coords:L.Coords,done:L.DoneCallback){
    const canvas=document.createElement('canvas');canvas.width=256;canvas.height=256;grid(canvas,coords)
    if(!props.tiles){setTimeout(()=>done(undefined,canvas),0);return canvas}
    const controller=new AbortController();pending.set(canvas,controller)
    void api<Blob>(`/geography/tiles/${coords.z}/${coords.x}/${coords.y}.png`,{responseType:'blob',signal:controller.signal}).then(async blob=>{
      const bitmap=await createImageBitmap(blob)
      try{if(alive&&!controller.signal.aborted){canvas.getContext('2d')?.drawImage(bitmap,0,0,256,256);loadedTiles++;emit('coverage',false)}}finally{bitmap.close()}
    }).catch(error=>{if(!isCancelled(error)&&alive&&!controller.signal.aborted){failedTiles++;if(!loadedTiles)emit('coverage',true)}}).finally(()=>{pending.delete(canvas);if(alive&&!controller.signal.aborted)done(undefined,canvas)})
    return canvas
  }})
  const tiles=new Tiles()
  L.setOptions(tiles,{tileSize:256,noWrap:true,keepBuffer:1,updateWhenIdle:true})
  tiles.on('tileunload',(event:L.TileEvent)=>{pending.get(event.tile)?.abort();pending.delete(event.tile)})
  tiles.addTo(map);markers=L.layerGroup().addTo(map);map.on('moveend',redraw)
  resize=new ResizeObserver(()=>map?.invalidateSize());resize.observe(host.value!);redraw()
})
watch(()=>props.points,redraw)
onBeforeUnmount(()=>{alive=false;resize?.disconnect();for(const control of pending.values())control.abort();pending.clear();map?.remove();map=undefined})
</script>
<template><div :class="{'map-selecting':selecting}"><div ref="host" class="business-map" role="region" aria-label="业务点位地图"></div></div></template>
