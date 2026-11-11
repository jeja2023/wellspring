import {test,expect} from '@playwright/test'

test('所有业务页面只在顶部栏显示页名，功能区及弹窗标题保留',async({page},testInfo)=>{
 await page.setViewportSize({width:1920,height:1080})
 await page.goto('/')
 await page.getByLabel('账号',{exact:true}).fill('superadmin')
 await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password')
 await page.getByRole('button',{name:'登录系统'}).click()
 const nav=page.getByRole('navigation',{name:'主导航'});await nav.waitFor()
 const names=await nav.getByRole('button').allTextContents()
 for(const name of names){
  await nav.getByRole('button',{name,exact:true}).click()
  await expect(page.getByRole('heading',{level:1,name,exact:true})).toHaveCount(1)
  await expect(page.locator('.content h1,.content .title-row,.content .intake-heading,.content .case-example-notice')).toHaveCount(0)
  await expect(page.locator('.content').getByRole('heading',{name,exact:true})).toHaveCount(0)
  if(['接警信息','案件管理'].includes(name))await page.screenshot({path:testInfo.outputPath(name==='接警信息'?'intake-without-duplicate-heading.png':'cases-without-duplicate-heading.png'),fullPage:true})
 }
 await nav.getByRole('button',{name:'案件管理',exact:true}).click()
 await expect(page.getByRole('heading',{name:'案件列表',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'新建案件',exact:true}).click()
 await expect(page.getByRole('dialog',{name:'新建案件草稿',exact:true}).getByRole('heading',{name:'新建案件草稿',exact:true})).toBeVisible()
})
