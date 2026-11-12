import {test,expect} from '@playwright/test'
import {fromMap,toMap} from '../src/features/geography/coordinates'

test('地图首次进入保留无锡中心和13级，级别随缩放更新',async({page},testInfo)=>{
  await page.setViewportSize({width:1440,height:1050});await page.goto('/')
  await page.getByLabel('账号',{exact:true}).fill('superadmin');await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password');await page.getByRole('button',{name:'登录系统',exact:true}).click();await page.getByRole('navigation',{name:'主导航'}).waitFor()
  await page.route('**/api/geography/config',async route=>{const response=await route.fetch();await route.fulfill({response,json:{...(await response.json()),tiles_available:true,tile_coordinate_system:'GCJ02',min_zoom:0,max_zoom:16,initial_view:{longitude:120.301663,latitude:31.574729,zoom:13}}})})
  if(!process.env.WELLSPRING_MAP_TILE_DIR)await page.route('**/api/geography/tiles/**',route=>route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC','base64')}))
  // A distant result must not replace the configured initial view.
  await page.route('**/api/geography/points',route=>route.fulfill({json:{items:[{resource_type:'PLACE',resource_id:'synthetic-far-point',name:'合成远处点位',longitude:116.4,latitude:39.9,version:1,source:'合成',place_id:'synthetic-far-point'}],total:1,truncated:false,limit:500}}))
  const tiles:number[][]=[];page.on('request',request=>{const match=request.url().match(/\/geography\/tiles\/(\d+)\/(\d+)\/(\d+)\.png/);if(match)tiles.push(match.slice(1).map(Number))})
  await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'业务地图',exact:true}).click()
  const level=page.getByLabel('当前地图级别',{exact:true})
  await expect(level).toHaveText('13 级');await expect(page.locator('.map-toolbar')).toContainText('1 / 1')
  await expect(page.getByText('业务空间分布',{exact:true})).toHaveCount(0);await expect(page.locator('.map-sidebar')).toHaveCount(0)
  await expect(page.getByRole('region',{name:'业务点位地图'})).not.toHaveClass(/leaflet-zoom-anim/)
  const before=await page.locator('.business-map').evaluate(element=>{const rect=element.getBoundingClientRect(),stage=element.closest('.map-canvas-stage')!;return {x:rect.x,y:rect.y,width:rect.width,height:rect.height,scrollX,scrollY,stageX:stage.scrollLeft,stageY:stage.scrollTop,pane:(element.querySelector('.leaflet-map-pane') as HTMLElement).style.transform}})
  const sampleMovement=()=>page.evaluate(async()=>{
    const samples=[]
    for(let index=0;index<24;index++){
      await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()))
      const element=document.querySelector('.business-map')!,rect=element.getBoundingClientRect(),stage=element.closest('.map-canvas-stage')!
      samples.push({x:rect.x,y:rect.y,width:rect.width,height:rect.height,scrollX,scrollY,stageX:stage.scrollLeft,stageY:stage.scrollTop,pane:(element.querySelector('.leaflet-map-pane') as HTMLElement).style.transform})
    }
    return samples
  })
  const opening=sampleMovement()
  const fullWidth=before.width
  await page.getByRole('button',{name:/^点位列表/}).click();await expect(page.locator('.map-sidebar')).toBeVisible();await expect.poll(()=>page.locator('.business-map').evaluate(element=>element.getBoundingClientRect().width)).toBe(fullWidth);await expect(page.getByRole('dialog',{name:/点位列表/})).toBeFocused()
  await expect(page.locator('.map-drawer')).not.toHaveClass(/map-drawer-enter-active/);await expect(page.locator('.map-drawer')).toHaveCSS('opacity','1')
  for(const sample of await opening)expect(sample).toEqual(before)
  await page.screenshot({path:testInfo.outputPath('map-point-list-drawer.png'),fullPage:true})
  const closing=sampleMovement()
  await page.getByRole('button',{name:'收起点位面板',exact:true}).click();await expect(page.locator('.map-sidebar')).toHaveCount(0);await expect(page.getByRole('button',{name:/^点位列表/})).toBeFocused()
  for(const sample of await closing)expect(sample).toEqual(before)
  const expectedX=Math.floor((120.301663+180)/360*2**13),latitude=31.574729*Math.PI/180,expectedY=Math.floor((1-Math.log(Math.tan(latitude)+1/Math.cos(latitude))/Math.PI)/2*2**13)
  await expect.poll(()=>tiles.some(([z,x,y])=>z===13&&x===expectedX&&y===expectedY)).toBe(true)
  await page.getByRole('button',{name:'放大',exact:true}).click();await expect(level).toHaveText('14 级')
  await page.getByRole('button',{name:'缩小',exact:true}).click();await expect(level).toHaveText('13 级')
  await expect(page.getByRole('region',{name:'业务点位地图'})).not.toHaveClass(/leaflet-zoom-anim/)
  if(process.env.WELLSPRING_MAP_TILE_DIR)await expect.poll(()=>page.locator('.business-map canvas[data-coverage=available]').count()).toBeGreaterThan(0)
  for(const size of [{width:1920,height:1080},{width:1440,height:900},{width:1366,height:768}]){
    await page.setViewportSize(size)
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1)).toBe(true)
    const mapBounds=await page.locator('.business-map').boundingBox()
    expect(mapBounds!.height).toBeGreaterThan(300)
    const stageHeight=await page.locator('.map-canvas-stage').evaluate(element=>element.getBoundingClientRect().height)
    expect(Math.abs(mapBounds!.height-stageHeight)).toBeLessThanOrEqual(1)
    const bottom=await page.locator('.map-panel').evaluate(element=>element.getBoundingClientRect().bottom)
    expect(size.height-bottom).toBeLessThanOrEqual(20)
  }
  await page.screenshot({path:testInfo.outputPath('wuxi-default-level-13.png'),fullPage:true})
  await page.setViewportSize({width:768,height:1000});await expect(level).toBeVisible();await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1)).toBe(true);await page.getByRole('button',{name:/^点位列表/}).click();await expect(page.getByRole('dialog',{name:/点位列表/})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight+1)).toBe(true);await page.keyboard.press('Escape');await expect(page.locator('.map-sidebar')).toHaveCount(0)
})

test('GCJ-02 离线底图显示和 WGS84 点选保存保持对齐',async({page},testInfo)=>{
  const external:string[]=[]
  page.on('request',request=>{if(request.url().startsWith('http')&&!['127.0.0.1','localhost'].includes(new URL(request.url()).hostname))external.push(request.url())})
  await page.setViewportSize({width:1440,height:1050});await page.goto('/')
  await page.getByLabel('账号',{exact:true}).fill('superadmin');await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password');await page.getByRole('button',{name:'登录系统',exact:true}).click();await page.getByRole('navigation',{name:'主导航'}).waitFor()
  // Always exercises GCJ-02, including on CI without user tiles.
  await page.route('**/api/geography/config',async route=>{const response=await route.fetch();await route.fulfill({response,json:{...(await response.json()),tiles_available:true,tile_coordinate_system:'GCJ02',min_zoom:0,max_zoom:16,initial_view:{longitude:120.083313,latitude:31.566835,zoom:16}}})})
  const native:[number,number]=[120.083313,31.566835],stored=fromMap(native,'GCJ02'),name='合成离线地图对齐-'+Date.now()
  await page.evaluate(async({name,stored})=>{
    const headers={Authorization:'Bearer '+sessionStorage.getItem('wellspring.session'),'Content-Type':'application/json'}
    const post=async(path:string,body:unknown)=>{const result=await fetch('/api'+path,{method:'POST',headers:{...headers,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});if(!result.ok)throw Error(await result.text());return result.json()}
    const row=await post('/places',{code:'SYNTHETIC-'+Date.now(),name,kind:'OTHER',district:'合成区域',address:'合成地址',responsible:'合成岗位',management_basis:'合成底图对齐验证'})
    await post(`/geography/PLACE/${row.id}/location`,{version:0,longitude:stored[0],latitude:stored[1],source:'合成 WGS84 对齐坐标'})
  },{name,stored})
  await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'业务地图',exact:true}).click();await page.getByLabel('查找点位',{exact:true}).fill(name);await page.getByRole('button',{name:'查询',exact:true}).click()
  const map=page.getByRole('region',{name:'业务点位地图'})
  await expect(page.locator('.map-basemap-status')).toContainText('GCJ-02');await expect(page.getByText('高德底图为 GCJ-02，业务坐标仍保存为 WGS84。点位显示和地图选点使用离线近似换算，位置须人工核对。',{exact:true})).toHaveCount(0)
  await expect(page.locator('.business-map .business-point')).toHaveCount(1)
  if(process.env.WELLSPRING_MAP_TILE_DIR)await expect.poll(()=>page.locator('.business-map canvas[data-coverage=available]').count()).toBeGreaterThan(0)
  const relative=await map.evaluate(element=>{const rect=element.querySelector('.business-point')!.getBoundingClientRect(),map=element.getBoundingClientRect();return {x:rect.x+rect.width/2-map.x,y:rect.y+rect.height/2-map.y,width:map.width,height:map.height}})
  expect(Math.abs(relative.x-relative.width/2)).toBeLessThan(3);expect(Math.abs(relative.y-relative.height/2)).toBeLessThan(3)
  await page.getByRole('button',{name:/^点位列表/}).click();await page.locator('.map-resource-list').getByRole('button').click();await page.getByRole('button',{name:'修改坐标',exact:true}).click();await expect(page.locator('.map-coordinate-editor')).toContainText('保存前请核对位置')
  // Offset from marker to avoid activating the marker instead of the map.
  await expect.poll(()=>map.evaluate(element=>{const marker=element.querySelector('.business-point');if(!marker)return 9999;const a=marker.getBoundingClientRect(),b=element.getBoundingClientRect();return Math.max(Math.abs(a.x+a.width/2-b.x-b.width/2),Math.abs(a.y+a.height/2-b.y-b.height/2))})).toBeLessThan(3)
  const size=await map.evaluate(element=>({width:element.getBoundingClientRect().width,height:element.getBoundingClientRect().height}))
  await map.click({position:{x:size.width/2+80,y:size.height/2}})
  const picked:[number,number]=[Number(await page.getByLabel('经度',{exact:true}).inputValue()),Number(await page.getByLabel('纬度',{exact:true}).inputValue())]
  const pickedNative=toMap(picked,'GCJ02'),expectedNativeLongitude=native[0]+80*360/(256*2**16)
  expect(Math.abs(pickedNative[0]-expectedNativeLongitude)).toBeLessThan(2*360/(256*2**16))
  expect(Math.abs(pickedNative[1]-native[1])).toBeLessThan(2*360/(256*2**16))
  await page.getByLabel('坐标来源 / 更正说明',{exact:true}).fill('合成高德底图点选近似换算核对');await page.getByRole('button',{name:'保存坐标',exact:true}).click();await expect(page.locator('.map-coordinate-summary')).toContainText('合成高德底图点选近似换算核对')
  await expect(page.getByRole('button',{name:'修改坐标',exact:true})).toBeEnabled()
  await page.screenshot({path:testInfo.outputPath('amap-native-tiles-and-wgs84-points.png'),fullPage:true})
  expect(external).toEqual([])
})
