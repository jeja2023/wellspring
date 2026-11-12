import {test,expect,type Page} from '@playwright/test'
async function login(page:Page,user:string){await page.goto('/');await page.getByLabel('账号',{exact:true}).fill(user);await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password');await page.getByRole('button',{name:'登录系统',exact:true}).click();await page.getByRole('navigation',{name:'主导航'}).waitFor()}

test('数据大屏顶部弹窗统计解读、全屏显示和关闭重开保留结果',async({page},testInfo)=>{
  await page.setViewportSize({width:1440,height:1000});await login(page,'superadmin')
  const user='statistics-reader-'+Date.now()
  await page.evaluate(async user=>{const headers={Authorization:'Bearer '+sessionStorage.getItem('wellspring.session'),'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},identity=await(await fetch('/api/session',{headers})).json();const response=await fetch('/api/system/users',{method:'POST',headers,body:JSON.stringify({username:user,password:'synthetic-test-password',org_id:identity.organization_id,is_admin:true})});if(!response.ok)throw Error(await response.text())},user)
  await page.getByRole('button',{name:'退出',exact:true}).click();await login(page,user)
  const nav=page.getByRole('navigation',{name:'主导航'});await nav.getByRole('button',{name:'数据大屏',exact:true}).click();await page.getByRole('combobox',{name:'新增统计周期',exact:true}).selectOption('7');await expect(page.locator('.screen-metric').first()).toContainText('近 7 天新增')
  const trigger=page.getByRole('button',{name:'AI 统计解读',exact:true});await expect(page.locator('.screen-toolbar').getByRole('button',{name:'AI 统计解读',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'前往 AI 统计解读',exact:true})).toHaveCount(0)
  let firstRead=true;const submissions:{mode:string;days:number;consent:boolean}[]=[]
  page.on('request',request=>{if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/ai/runs')submissions.push(request.postDataJSON())})
  await page.route('**/api/ai/runs/*',async route=>{if(route.request().method()!=='GET'||!firstRead)return route.continue();firstRead=false;const response=await route.fetch();await route.fulfill({response,json:{...(await response.json()),status:'RUNNING',output_text:''}})})
  await page.getByRole('button',{name:'全屏展示',exact:true}).click();await expect(page.locator('.data-screen')).toHaveClass(/is-fullscreen/)
  await trigger.click();const dialog=page.getByRole('dialog',{name:'AI 统计解读',exact:true});await expect(dialog).toBeVisible();await expect(dialog).toContainText('近 7 天');const generate=dialog.getByRole('button',{name:'生成统计解读',exact:true});await expect(generate).toBeDisabled()
  await dialog.getByRole('checkbox',{name:'我已确认将汇总统计发送至已配置的模型服务。',exact:true}).check();await generate.click();await expect(dialog.getByText('正在生成统计解读，可关闭弹窗后再打开查看。',{exact:true})).toBeVisible()
  await dialog.getByRole('button',{name:'关闭AI 统计解读',exact:true}).click();await expect(dialog).toHaveCount(0);await expect(page.locator('.data-screen')).toHaveClass(/is-fullscreen/)
  await trigger.click();await expect(dialog.locator('.statistics-result')).toContainText('合成研判结果');await expect(dialog.locator('.statistics-result')).toContainText('<script>不得执行</script>');await expect(dialog.locator('.statistics-result script')).toHaveCount(0)
  expect(submissions).toHaveLength(1);expect(submissions[0]).toMatchObject({mode:'dashboard',days:7,consent:true});await expect(page.getByRole('heading',{level:1,name:'数据大屏',exact:true})).toHaveCount(1)
  await page.screenshot({path:testInfo.outputPath('screen-statistics-interpretation-dialog.png'),fullPage:true})
  await dialog.getByRole('button',{name:'关闭AI 统计解读',exact:true}).click();await page.getByRole('button',{name:'退出全屏',exact:true}).click();await page.setViewportSize({width:768,height:900});await trigger.click();await expect(dialog.locator('.statistics-result')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await dialog.getByRole('button',{name:'关闭AI 统计解读',exact:true}).click()
  await page.getByRole('button',{name:'退出',exact:true}).click();await login(page,'outsider');await nav.getByRole('button',{name:'数据大屏',exact:true}).click();await expect(page.getByRole('button',{name:'AI 统计解读',exact:true})).toHaveCount(0)
})
