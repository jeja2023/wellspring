import {test,expect,type Page} from '@playwright/test'
import ExcelJS from 'exceljs'

async function login(page:Page,username:string){await page.goto('/');await page.getByLabel('账号',{exact:true}).fill(username);await page.getByLabel('密码',{exact:true}).fill('synthetic-test-password');await page.getByRole('button',{name:'登录系统'}).click();await page.getByRole('navigation',{name:'主导航'}).waitFor()}
async function logout(page:Page){await page.getByRole('button',{name:'退出',exact:true}).click()}
async function received(page:Page,title:string){await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'情报线索',exact:true}).click();await page.getByRole('button',{name:'收到的线索',exact:true}).click();await page.locator('.intelligence-flow tbody tr').filter({hasText:title}).getByRole('button',{name:'查看办理',exact:true}).click()}

test('Excel录入、支队下发大队、派出所处置反馈及逐级复核办结',async({page},testInfo)=>{
  test.setTimeout(90000)
  await page.setViewportSize({width:1440,height:1000});await login(page,'superadmin')
  const stamp=Date.now().toString(),title='层级闭环-'+stamp
  const setup=await page.evaluate(async(stamp)=>{
    const headers={Authorization:'Bearer '+sessionStorage.getItem('wellspring.session'),'Content-Type':'application/json'}
    const post=async(path:string,body:unknown)=>{const response=await fetch('/api'+path,{method:'POST',headers:{...headers,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});if(!response.ok)throw Error(await response.text());return response.json()}
    const identity=await(await fetch('/api/session',{headers})).json(),options=await(await fetch('/api/system/options',{headers})).json()
    const current=options.organizations.find((row:{id:string})=>row.id===identity.organization_id)
    await post(`/system/organizations/${current.id}/update`,{name:current.name,parent_id:current.parent_id,active:true,unit_type:'CITY',version:current.version})
    const brigade=await post('/system/organizations',{name:'合成分局大队-'+stamp,parent_id:current.id,unit_type:'BRANCH'})
    const station=await post('/system/organizations',{name:'合成派出所-'+stamp,parent_id:brigade.id,unit_type:'STATION'})
    for(const [name,org] of [['brigade-'+stamp,brigade.id],['station-'+stamp,station.id]])await post('/system/users',{username:name,password:'synthetic-test-password',org_id:org,role_id:'wellspring-business-user'})
    return {brigade:brigade.id,station:station.id}
  },stamp)
  const book=new ExcelJS.Workbook(),sheet=book.addWorksheet('线索导入');sheet.addRow(['线索编号','标题','来源','线索内容','办理期限','重要程度']);sheet.addRow(['FLOW-'+stamp,title,'合成Excel','合成层级处置原文','2030-01-10','普通']);sheet.addRow(['IMPORTANT-'+stamp,'重要-'+title,'合成Excel','重要合成线索，不得下发派出所','','重要'])
  const nav=page.getByRole('navigation',{name:'主导航'});await nav.getByRole('button',{name:'情报线索',exact:true}).click();await page.getByRole('button',{name:'Excel 导入 / 记录',exact:true}).click()
  await page.locator('.flow-import-panel input[type=file]').setInputFiles({name:'synthetic-clues.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:Buffer.from(await book.xlsx.writeBuffer())})
  await expect(page.getByRole('dialog',{name:'核对导入线索',exact:true})).toBeVisible();await page.getByRole('button',{name:'确认导入 2 条线索',exact:true}).click()
  await expect(page.getByRole('status')).toContainText('已导入 2 条线索')
  await page.getByRole('button',{name:'本级线索',exact:true}).click()
  await page.getByRole('row').filter({hasText:'重要-'+title}).getByRole('button',{name:'查看',exact:true}).click()
  await page.getByLabel('核验说明',{exact:true}).fill('合成重要线索核验');await page.getByRole('button',{name:'记录核验',exact:true}).click();await page.getByRole('button',{name:'下发线索至下级单位',exact:true}).click()
  await expect(page.getByRole('checkbox',{name:'允许继续下发派出所',exact:true})).toBeDisabled();await page.getByRole('dialog',{name:'下发情报线索',exact:true}).getByRole('button',{name:/^关闭/}).click()
  await page.getByRole('row').filter({hasText:'FLOW-'+stamp}).getByRole('button',{name:'查看',exact:true}).click();await page.getByLabel('核验说明',{exact:true}).fill('合成核验通过');await page.getByRole('button',{name:'记录核验',exact:true}).click()
  await page.getByRole('button',{name:'下发线索至下级单位',exact:true}).click();await page.getByRole('combobox',{name:'接收单位',exact:true}).selectOption(setup.brigade);await page.getByLabel('办理要求',{exact:true}).fill('大队组织核查并汇总反馈');await page.getByRole('checkbox',{name:'允许继续下发派出所',exact:true}).check();await page.getByRole('combobox',{name:'接收单位',exact:true}).selectOption(setup.brigade);await page.getByRole('button',{name:'确认下发',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0)
  await logout(page);await login(page,'brigade-'+stamp);await received(page,title);await page.getByRole('button',{name:'接收并由我承办',exact:true}).click();await page.getByRole('button',{name:'继续下发下级单位',exact:true}).click();await page.getByRole('checkbox',{name:'允许继续下发派出所',exact:true}).check();await page.getByRole('combobox',{name:'接收单位',exact:true}).selectOption(setup.station);await page.getByLabel('办理要求',{exact:true}).fill('派出所核查并反馈');await page.getByRole('button',{name:'确认下发',exact:true}).click();await expect(page.getByRole('button',{name:'向上级提交反馈',exact:true})).toBeDisabled()
  await logout(page);await login(page,'station-'+stamp);await received(page,title);await page.getByRole('button',{name:'接收并由我承办',exact:true}).click();await page.getByLabel('本次处置',{exact:true}).fill('已开展合成核查');await page.getByRole('button',{name:'保存处置记录',exact:true}).click();await page.getByLabel('处置经过',{exact:true}).fill('核查合成场所及来源');await page.getByLabel('反馈内容',{exact:true}).fill('合成反馈，需要上级核验');await page.getByRole('button',{name:'向上级提交反馈',exact:true}).click();await expect(page.locator('.flow-detail')).toContainText('待复核')
  await logout(page);await login(page,'brigade-'+stamp);await received(page,title);await page.locator('.flow-detail').getByRole('row').filter({hasText:'合成派出所-'+stamp}).getByRole('button',{name:'查看办理',exact:true}).click();await page.getByLabel('复核意见',{exact:true}).fill('大队已核验反馈依据');await page.getByRole('button',{name:'复核办结',exact:true}).click()
  await page.locator('.intelligence-flow>.card').first().getByRole('row').filter({hasText:title}).getByRole('button',{name:'查看办理',exact:true}).click();await page.getByLabel('处置经过',{exact:true}).fill('大队组织核查并复核派出所反馈');await page.getByLabel('反馈内容',{exact:true}).fill('大队汇总反馈结论');await page.getByRole('button',{name:'向上级提交反馈',exact:true}).click()
  await logout(page);await login(page,'superadmin');await nav.getByRole('button',{name:'情报线索',exact:true}).click();await page.getByRole('button',{name:'我下发的线索',exact:true}).click();await page.locator('.intelligence-flow tbody tr').filter({hasText:title}).getByRole('button',{name:'查看办理',exact:true}).click();await page.getByLabel('复核意见',{exact:true}).fill('支队复核，闭环办结');await page.getByRole('button',{name:'复核办结',exact:true}).click();await expect(page.locator('.flow-detail')).toContainText('已办结');await expect(page.locator('.flow-timeline')).toContainText('支队复核，闭环办结')
  await page.screenshot({path:testInfo.outputPath('intelligence-hierarchical-closed-loop.png'),fullPage:true})
})
