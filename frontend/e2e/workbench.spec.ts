import {test,expect} from '@playwright/test'

test('工作台聚焦办理、全量逾期、独立复核和直接打开工单，统计由大屏展示',async({page},testInfo)=>{
  await page.goto('/');await page.getByLabel('账号',{exact:true}).fill('superadmin');await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password');await page.getByRole('button',{name:'登录系统',exact:true}).click()
  const nav=page.getByRole('navigation',{name:'主导航'});await expect(nav).toBeVisible()
  const created=await page.evaluate(async()=>{
    const base={Authorization:'Bearer '+sessionStorage.getItem('wellspring.session'),'Content-Type':'application/json'}
    const post=async(path:string,body:unknown,authorization=base.Authorization)=>{const response=await fetch('/api'+path,{method:'POST',headers:{...base,Authorization:authorization,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});if(!response.ok)throw Error(await response.text());return response.json()}
    const identity=await(await fetch('/api/session',{headers:base})).json()
    const users=await(await fetch('/api/intelligence/assignees',{headers:base})).json()
    const receiver=users.find((user:{username:string})=>user.username==='receiver')
    const other=await post('/login',{username:'receiver',password:'synthetic-test-password'})
    const rows=[]
    for(const [index,assignee] of [users.find((user:{username:string})=>user.username===identity.username).id,receiver.id].entries()){
      const title='合成工作台工单-'+Date.now()+'-'+index
      const clue=await post('/intelligence/clues',{title,summary:'合成办理事项',source:'浏览器回归'})
      const reviewed=await post(`/intelligence/clues/${clue.id}/review`,{version:1,note:'合成核验'})
      const task=await post(`/intelligence/clues/${clue.id}/tasks`,{clue_version:reviewed.version,objective:'合成办理',assignee_id:assignee,due_date:'2000-01-01'})
      if(index)await post(`/intelligence/tasks/${task.id}/transition`,{version:task.version,action:'SUBMIT',result:'NO_FINDING',note:'合成反馈'},'Bearer '+other.token)
      rows.push({title,id:clue.id})
    }
    await post('/logout',{},'Bearer '+other.token)
    return rows
  })
  await page.getByRole('button',{name:'刷新事项',exact:true}).click()
  const table=page.getByRole('table',{name:'工作台办理事项',exact:true})
  await expect(table).toContainText(created[0].title)
  await expect(page.locator('.workbench-summary-item')).toHaveCount(4)
  await expect(page.locator('.content .metrics,.content .screen-metric')).toHaveCount(0)
  await page.getByRole('combobox',{name:'业务模块',exact:true}).selectOption('intelligence')
  await page.getByRole('button',{name:/^已逾期/}).click()
  await expect(table).toContainText(created[0].title)
  await expect(table.getByRole('row').filter({hasText:created[0].title})).toContainText('逾期')
  await table.getByRole('row').filter({hasText:created[0].title}).getByRole('button',{name:'查看办理',exact:true}).click()
  await expect(page.getByRole('heading',{level:1,name:'情报线索',exact:true})).toBeVisible()
  await expect(page.getByRole('heading',{name:created[0].title,exact:true})).toBeVisible()
  await nav.getByRole('button',{name:'工作台',exact:true}).click()
  await page.getByRole('button',{name:/^待复核/}).click();await expect(table).toContainText(created[1].title)
  await table.getByRole('row').filter({hasText:created[1].title}).getByRole('button',{name:'查看办理',exact:true}).click()
  await expect(page.getByRole('heading',{name:created[1].title,exact:true})).toBeVisible()
  await nav.getByRole('button',{name:'工作台',exact:true}).click()
  await page.getByRole('button',{name:'登记案件',exact:false}).click()
  await expect(page.getByRole('dialog',{name:'新建案件',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'关闭新建案件',exact:true}).click()
  await nav.getByRole('button',{name:'工作台',exact:true}).click();await page.getByRole('button',{name:'查看业务统计',exact:true}).click()
  await expect(page.locator('.screen-metric')).toHaveCount(6)
  await nav.getByRole('button',{name:'工作台',exact:true}).click();await expect(table).toBeVisible()
  await page.screenshot({path:testInfo.outputPath('workbench-actions.png'),fullPage:true})
  await page.setViewportSize({width:768,height:1000});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:testInfo.outputPath('workbench-768.png'),fullPage:true})
})
