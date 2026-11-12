import test from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import Module from 'node:module'
import path from 'node:path'
const bundle=await build({entryPoints:['src/features/geography/coordinates.ts'],bundle:true,platform:'node',format:'cjs',write:false})
const compiled=new Module(path.resolve('tests/map-coordinates.bundle.cjs'))
compiled.filename=path.resolve('tests/map-coordinates.bundle.cjs')
compiled._compile(bundle.outputFiles[0].text,compiled.filename)
const {toMap,fromMap,toWgsBounds}=compiled.exports

test('高德底图显示换算与点选反算保留统一 WGS84 业务坐标',()=>{
  const original=[116.404,39.915],mapped=toMap(original,'GCJ02')
  assert.ok(Math.abs(mapped[0]-116.41024449916938)<1e-10)
  assert.ok(Math.abs(mapped[1]-39.91640428150164)<1e-10)
  for(const point of [original,[120.061340,31.550453],[113.26,23.13],[104.06,30.67],[-73.98,40.75]]){
    const result=fromMap(toMap(point,'GCJ02'),'GCJ02')
    assert.ok(Math.abs(result[0]-point[0])<1e-7);assert.ok(Math.abs(result[1]-point[1])<1e-7)
    assert.deepEqual(toMap(point,'WGS84'),point);assert.deepEqual(fromMap(point,'WGS84'),point)
  }
  assert.deepEqual(original,[116.404,39.915])
})

test('高德视野查询换算回 WGS84 并覆盖抽样边界，WGS84 底图不偏移',()=>{
  const view=[119.9,31.4,120.2,31.7],bounds=toWgsBounds(view,'GCJ02')
  for(let x=0;x<=20;x++)for(let y=0;y<=20;y++){
    const point=fromMap([view[0]+(view[2]-view[0])*x/20,view[1]+(view[3]-view[1])*y/20],'GCJ02')
    assert.ok(point[0]>=bounds[0]&&point[0]<=bounds[2]&&point[1]>=bounds[1]&&point[1]<=bounds[3])
  }
  assert.deepEqual(toWgsBounds(view,'WGS84'),view)
})
