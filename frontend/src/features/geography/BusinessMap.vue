<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref,watch} from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {useWorkspace} from '../../app/workspace'
import {isCancelled} from '../../shared/api/client'
import {layerColors,layerNames,type GeoResource} from './types'
import {fromMap,toMap,toWgsBounds,type CoordinateSystem} from './coordinates'
const props=defineProps<{points:GeoResource[];tiles:boolean;selecting?:boolean;tileCrs?:CoordinateSystem;minZoom?:number;maxZoom?:number;initialView?:{longitude:number;latitude:number;zoom:number}}>()
const emit=defineEmits<{select:[point:GeoResource];pick:[longitude:number,latitude:number];coverage:[missing:boolean]}>()
const {api}=useWorkspace(),host=ref<HTMLElement>()
const zoom=ref(props.initialView?.zoom??13)
let map:L.Map|undefined,markers:L.LayerGroup|undefined,resize:ResizeObserver|undefined
const pending=new Map<HTMLElement,AbortController>()
let alive=true
function system():CoordinateSystem{return props.tiles?(props.tileCrs||'WGS84'):'GCJ02'}
function position(row:GeoResource):L.LatLngTuple{const [longitude,latitude]=toMap([row.longitude!,row.latitude!],system());return [latitude,longitude]}
function coverage(){
  if(!alive||!host.value||!props.tiles)return
  const view=host.value.getBoundingClientRect()
  const visible=Array.from(host.value.querySelectorAll<HTMLCanvasElement>('canvas.leaflet-tile')).filter(tile=>{
    const box=tile.getBoundingClientRect();return box.right>view.left&&box.left<view.right&&box.bottom>view.top&&box.top<view.bottom
  })
  emit('coverage',visible.some(tile=>tile.dataset.coverage==='missing'))
}
function grid(canvas:HTMLCanvasElement,coords:L.Coords){
  const ctx=canvas.getContext('2d');if(!ctx)return
  const styles=getComputedStyle(document.documentElement)
  const bg=styles.getPropertyValue('--ws-bg-subtle').trim()||'#f8fbfe'
  const stroke=styles.getPropertyValue('--ws-border-default').trim()||'#dce5ef'
  const text=styles.getPropertyValue('--ws-text-muted').trim()||'#64748b'
  ctx.fillStyle=bg;ctx.fillRect(0,0,256,256);ctx.strokeStyle=stroke;ctx.lineWidth=1
  for(let i=0;i<=256;i+=64){ctx.beginPath();ctx.moveTo(i,0);ctx.lineTo(i,256);ctx.moveTo(0,i);ctx.lineTo(256,i);ctx.stroke()}
  const corner=L.CRS.EPSG3857.pointToLatLng(L.point(coords.x*256,coords.y*256),coords.z)
  ctx.fillStyle=text;ctx.font='11px sans-serif';ctx.fillText(`${corner.lng.toFixed(3)}°, ${corner.lat.toFixed(3)}°`,8,18)
}
function redraw(){
  if(!map||!markers)return;markers.clearLayers()
  const buckets=new Map<string,GeoResource[]>()
  for(const row of props.points){if(row.longitude===null||row.latitude===null)continue
    const xy=map.latLngToContainerPoint(position(row)),key=`${Math.floor(xy.x/36)}:${Math.floor(xy.y/36)}`
    const bucket=buckets.get(key)||[];bucket.push(row);buckets.set(key,bucket)
  }
  for(const rows of buckets.values()){
    const row=rows[0],cluster=rows.length>1
    const icon=L.divIcon({className:'business-point'+(cluster?' business-cluster':''),html:cluster?String(rows.length):`<span style="background:${layerColors[row.resource_type]}"></span>`,iconSize:cluster?[32,32]:[24,24],iconAnchor:cluster?[16,16]:[12,12]})
    const title=cluster?`${rows.length} 个相邻点位`:`${layerNames[row.resource_type]}：${row.name}`
    const marker=L.marker(position(row),{icon,title,alt:title,keyboard:true}).addTo(markers)
    const tooltip=document.createElement('span');tooltip.textContent=title;marker.bindTooltip(tooltip)
    marker.on('click',()=>{
      if(!cluster){emit('select',row);return}
      const list=document.createElement('div');list.className='map-cluster-list'
      for(const item of rows){const button=document.createElement('button');button.type='button';button.textContent=`${layerNames[item.resource_type]} · ${item.name}`;button.addEventListener('click',()=>{emit('select',item);map?.closePopup()});list.append(button)}
      marker.bindPopup(list,{maxHeight:220}).openPopup()
    })
  }
}
function fit(){if(!map)return;const coords=props.points.filter(row=>row.latitude!==null&&row.longitude!==null).map(row=>L.latLng(position(row)));if(coords.length)map.fitBounds(L.latLngBounds(coords),{padding:[45,45],maxZoom:Math.min(16,map.getMaxZoom())})}
function focus(row:GeoResource){if(map&&row.latitude!==null&&row.longitude!==null)map.setView(position(row),Math.min(map.getMaxZoom(),Math.max(map.getZoom(),16)))}
function bounds():[number,number,number,number]|undefined{if(!map)return;const b=map.getBounds();return toWgsBounds([Math.max(-180,b.getWest()),Math.max(-85,b.getSouth()),Math.min(180,b.getEast()),Math.min(85,b.getNorth())],system())}
defineExpose({fit,focus,bounds})
onMounted(()=>{
  const [defaultLongitude,defaultLatitude]=system()==='GCJ02'?[120.301663,31.574729]:fromMap([120.301663,31.574729],'GCJ02')
  const initialPos=props.initialView?toMap([props.initialView.longitude,props.initialView.latitude],system()):[defaultLongitude,defaultLatitude]
  const initialZoom=props.initialView?.zoom??13
  map=L.map(host.value!,{zoomControl:false,minZoom:props.minZoom??0,maxZoom:props.maxZoom??20,maxBounds:[[-85,-180],[85,180]],maxBoundsViscosity:1}).setView([initialPos[1],initialPos[0]],initialZoom)
  zoom.value=map.getZoom();map.on('zoomend',()=>{if(map)zoom.value=map.getZoom()})
  L.control.zoom({zoomInTitle:'放大',zoomOutTitle:'缩小'}).addTo(map);L.control.scale({imperial:false}).addTo(map)
  map.attributionControl.setPrefix('');map.on('click',(event:L.LeafletMouseEvent)=>{if(props.selecting){const [longitude,latitude]=fromMap([event.latlng.lng,event.latlng.lat],system());emit('pick',Number(longitude.toFixed(6)),Number(latitude.toFixed(6)))}})
  if(props.tiles){
    const Tiles=L.GridLayer.extend({createTile(coords:L.Coords,done:L.DoneCallback){
      const canvas=document.createElement('canvas');canvas.width=256;canvas.height=256;grid(canvas,coords)
      const controller=new AbortController();pending.set(canvas,controller)
      void api<Blob>(`/geography/tiles/${coords.z}/${coords.x}/${coords.y}.png`,{responseType:'blob',signal:controller.signal}).then(async blob=>{
        const bitmap=await createImageBitmap(blob)
        try{if(alive&&!controller.signal.aborted){canvas.getContext('2d')?.drawImage(bitmap,0,0,256,256);canvas.dataset.coverage='available'}}finally{bitmap.close()}
      }).catch(error=>{if(!isCancelled(error)&&alive&&!controller.signal.aborted)canvas.dataset.coverage='missing'}).finally(()=>{pending.delete(canvas);if(alive&&!controller.signal.aborted){done(undefined,canvas);coverage()}})
      return canvas
    }})
    const tiles=new Tiles()
    L.setOptions(tiles,{tileSize:256,noWrap:true,keepBuffer:1,updateWhenIdle:true})
    tiles.on('tileunload',(event:L.TileEvent)=>{pending.get(event.tile)?.abort();pending.delete(event.tile)})
    tiles.addTo(map)
  }else{
    const onlineTiles=L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',{
      subdomains:['1','2','3','4'],
      minZoom:props.minZoom??3,
      maxZoom:props.maxZoom??18,
      attribution:'© 高德地图'
    })
    onlineTiles.addTo(map)
  }
  markers=L.layerGroup().addTo(map);map.on('moveend',()=>{redraw();coverage()})
  resize=new ResizeObserver(()=>map?.invalidateSize());resize.observe(host.value!);redraw()
})
watch(()=>props.points,redraw)
onBeforeUnmount(()=>{alive=false;resize?.disconnect();for(const control of pending.values())control.abort();pending.clear();map?.remove();map=undefined})
</script>
<template><div class="business-map-shell" :class="{'map-selecting':selecting}"><div ref="host" class="business-map" role="region" aria-label="业务点位地图"></div><output class="map-zoom-level" aria-label="当前地图级别" aria-live="polite">{{zoom}} 级</output></div></template>
