import {test,expect} from '@playwright/test'

test('全部业务表格序号、完整边框及分页样式统一',async({page},testInfo)=>{
 await page.setViewportSize({width:1920,height:1080})
 await page.goto('/')
 await page.getByLabel('账号',{exact:true}).fill('superadmin')
 await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password')
 await page.getByRole('button',{name:'登录系统'}).click()
 const nav=page.getByRole('navigation',{name:'主导航'})
 await nav.waitFor()
 await page.evaluate(async()=>{
  const headers={Authorization:'Bearer '+sessionStorage.getItem('wellspring.session'),'Content-Type':'application/json'}
  const post=async(path:string,body:unknown)=>{const response=await fetch('/api'+path,{method:'POST',headers:{...headers,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});if(!response.ok)throw Error(await response.text());return response.json()}
  const users=await(await fetch('/api/intelligence/assignees',{headers})).json()
  const clue=await post('/intelligence/clues',{title:'合成表格待办',summary:'表格布局验证',source:'合成'})
  const reviewed=await post(`/intelligence/clues/${clue.id}/review`,{version:1,note:'合成核验'})
  await post(`/intelligence/clues/${clue.id}/tasks`,{clue_version:reviewed.version,objective:'合成待办',assignee_id:users.find((u:{username:string})=>u.username==='superadmin').id})
 })
 await nav.getByRole('button',{name:'案件管理',exact:true}).click()
 let checked=0
 for(const name of ['工作台','接警信息','案件管理','证物管理','情报线索','人员档案','操作记录','用户管理','角色管理','组织管理','系统日志']){
  await nav.getByRole('button',{name,exact:true}).click()
  const tables=page.locator('.content table:visible')
  await expect.poll(()=>tables.count()).toBeGreaterThan(0)
  for(const table of await tables.all()){
   await expect(table.locator('thead th').first()).toHaveText('序号')
   const bordered=await table.evaluate(element=>[...element.querySelectorAll('th,td')].every(cell=>{
    const s=getComputedStyle(cell);return ['Top','Right','Bottom','Left'].every(side=>parseFloat(s['border'+side+'Width' as keyof CSSStyleDeclaration] as string)>0)
   }))
   expect(bordered).toBe(true);checked++
  }
  for(const pagination of await page.locator('.pagination:visible').all()){
   expect(['flex-end','end','flow-end']).toContain(await pagination.evaluate(el=>getComputedStyle(el).justifyContent))
   await expect(pagination.getByRole('button',{name:'首页',exact:true})).toBeVisible()
   await expect(pagination.getByRole('button',{name:'末页',exact:true})).toBeVisible()
  }
 }
 await nav.getByRole('button',{name:'污水监测',exact:true}).click()
 for(const name of ['采样点','采样记录','检测结果']){
  await page.getByRole('tab',{name,exact:true}).click()
  await expect(page.locator('table thead th').first()).toHaveText('序号');checked++
 }
 await page.screenshot({path:testInfo.outputPath('uniform-table-pagination.png'),fullPage:true})
 expect(checked).toBeGreaterThanOrEqual(14)
 await page.setViewportSize({width:768,height:900})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})

test('共享分页首页末页、数字页和跳转保持序号与列表一致',async({page})=>{
 await page.goto('/')
 await page.getByLabel('账号',{exact:true}).fill('superadmin')
 await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password')
 await page.getByRole('button',{name:'登录系统'}).click()
 const nav=page.getByRole('navigation',{name:'主导航'});await nav.waitFor()
 await page.route('**/api/cases?*',async route=>{
  const target=Number(new URL(route.request().url()).searchParams.get('page')||1)
  if(target===4)return route.fulfill({status:500,json:{code:'SYNTHETIC_FAILURE',message:'合成翻页失败'}})
  await route.fulfill({json:{items:Array.from({length:20},(_,i)=>({id:`case-${target}-${i}`,number:`PAGE-${target}-${i}`,title:'分页合成案件',status:'DRAFT'})),page:target,page_size:20,total:120,has_more:target<6}})
 })
 await nav.getByRole('button',{name:'案件管理',exact:true}).click()
 const controls=page.getByRole('navigation',{name:'数据分页'})
 const first=page.locator('.content tbody tr').first().locator('td').first()
 await expect(first).toHaveText('1')
 await controls.getByRole('button',{name:'下一页',exact:true}).click();await expect(first).toHaveText('21')
 await controls.getByRole('button',{name:'末页',exact:true}).click();await expect(first).toHaveText('101')
 await expect(controls.getByRole('button',{name:'下一页',exact:true})).toBeDisabled()
 await controls.getByRole('spinbutton',{name:'目标页码'}).fill('3')
 await controls.getByRole('button',{name:'跳转',exact:true}).click();await expect(first).toHaveText('41')
 await controls.getByRole('button',{name:'第 4 页',exact:true}).click()
 await expect(page.getByRole('alert')).toContainText('合成翻页失败')
 await expect(first).toHaveText('41');await expect(controls).toContainText('第 3 页 · 共 120 条')
 await controls.getByRole('button',{name:'首页',exact:true}).click();await expect(first).toHaveText('1')
 await expect(controls.getByRole('button',{name:'上一页',exact:true})).toBeDisabled()
})
