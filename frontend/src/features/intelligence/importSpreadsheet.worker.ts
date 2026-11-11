import {parse} from './importSpreadsheet'
self.onmessage=async(event:MessageEvent<{buffer:ArrayBuffer}>)=>{try{self.postMessage({rows:await parse(event.data.buffer)})}catch(e){self.postMessage({error:e instanceof Error?e.message:'Excel 解析失败'})}}
