import {test,expect,type Page} from '@playwright/test'

async function login(page:Page,user:string){await page.goto('/');await page.getByLabel('账号',{exact:true}).fill(user);await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password');await page.getByRole('button',{name:'登录系统',exact:true}).click();await page.getByRole('navigation',{name:'主导航'}).waitFor()}

test('中文操作记录筛选、日期对象查询和两页15条分页',async({page},testInfo)=>{
  await page.setViewportSize({width:1440,height:1000});await login(page,'superadmin')
  const user='audit-reader-'+Date.now()
  await page.evaluate(async user=>{
    const headers={Authorization:'Bearer '+sessionStorage.getItem('wellspring.session'),'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()}
    const identity=await(await fetch('/api/session',{headers})).json()
    const response=await fetch('/api/system/users',{method:'POST',headers,body:JSON.stringify({username:user,password:'synthetic-test-password',org_id:identity.organization_id,role_id:'wellspring-business-user'})})
    if(!response.ok)throw Error(await response.text())
  },user)
  await page.getByRole('button',{name:'退出',exact:true}).click();await login(page,user)
  const target=await page.evaluate(async()=>{
    const headers={Authorization:'Bearer '+sessionStorage.getItem('wellspring.session'),'Content-Type':'application/json'},ids:string[]=[]
    for(let index=0;index<24;index++){
      const response=await fetch('/api/cases',{method:'POST',headers:{...headers,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({number:'SYNTHETIC-AUDIT-'+Date.now()+'-'+index,title:'合成审计分页案件'})})
      if(!response.ok)throw Error(await response.text());ids.push((await response.json()).id)
    }
    return ids[0]
  })
  const date=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai'}).format(new Date())
  await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'操作记录',exact:true}).click()
  const own=page.getByRole('table',{name:'本人操作记录',exact:true})
  await expect(own.getByRole('columnheader',{name:'操作内容',exact:true})).toBeVisible();await expect(own.getByRole('columnheader',{name:/北京时间/})).toHaveCount(0)
  await page.getByLabel('操作内容',{exact:true}).fill('创建案件记录');await page.getByLabel('开始日期',{exact:true}).fill(date);await page.getByLabel('结束日期',{exact:true}).fill(date);await page.getByRole('button',{name:'查询',exact:true}).click()
  await expect(own.locator('tbody tr')).toHaveCount(15);await expect(page.locator('.pagination-summary')).toContainText('共 24 条');await expect(page.locator('.pagination-size')).toHaveText('每页 15 条')
  await expect(own.locator('tbody')).not.toContainText('CASE_CREATE')
  await page.getByRole('button',{name:'下一页',exact:true}).click();await expect(own.locator('tbody tr')).toHaveCount(9);await expect(own.locator('tbody tr').first().locator('td').first()).toHaveText('16')
  await page.getByLabel('对象标识',{exact:true}).fill(target);await page.getByRole('button',{name:'查询',exact:true}).click();await expect(own.locator('tbody tr')).toHaveCount(1);await expect(own.locator('tbody')).toContainText(target);await expect(own.locator('tbody tr').first().locator('td').first()).toHaveText('1')
  await page.getByRole('button',{name:'重置',exact:true}).click();await expect(page.getByLabel('操作内容',{exact:true})).toHaveValue('');await expect(page.getByLabel('开始日期',{exact:true})).toHaveValue('');await expect(own.locator('tbody tr')).toHaveCount(15)
  await page.screenshot({path:testInfo.outputPath('personal-history-chinese-filters.png'),fullPage:true})
  await page.getByRole('button',{name:'退出',exact:true}).click();await login(page,'superadmin');await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'系统日志',exact:true}).click()
  const system=page.getByRole('table',{name:'系统日志记录',exact:true});await page.getByLabel('操作账号',{exact:true}).fill(user);await page.getByLabel('操作内容',{exact:true}).fill('创建案件记录');await page.getByRole('button',{name:'查询',exact:true}).click()
  await expect(system.locator('tbody tr')).toHaveCount(15);await expect(page.locator('.pagination-size')).toHaveText('每页 15 条');await expect(system.locator('tbody')).not.toContainText('CASE_CREATE');await expect(system.getByRole('columnheader',{name:/北京时间|操作代码/})).toHaveCount(0)
  await page.getByRole('button',{name:'下一页',exact:true}).click();await expect(system.locator('tbody tr')).toHaveCount(9);await expect(system.locator('tbody tr').first().locator('td').first()).toHaveText('16')
  await page.screenshot({path:testInfo.outputPath('system-history-chinese-pagination.png'),fullPage:true});await page.setViewportSize({width:768,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
