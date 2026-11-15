// Shared headless-Chrome launcher for the *-browser.cjs tests (Node's built-in WebSocket, no deps).
'use strict';
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process');
const chromePath=[process.env.CHROME_PATH,'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/usr/bin/chromium','/usr/bin/google-chrome'].filter(Boolean).find(p=>fs.existsSync(p));
function requireChrome(){if(!chromePath){console.error('FAIL: no Chrome/Chromium found; set CHROME_PATH. This browser test was NOT run.');process.exit(1);}return chromePath;}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function launch(extraArgs=[]){
  requireChrome();
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ftv-browser-'));
  const proc=spawn(chromePath,['--headless=new','--remote-debugging-port=0','--user-data-dir='+dir,'--no-first-run','--no-default-browser-check','--mute-audio','--window-size=1920,1080',...extraArgs,'about:blank'],{stdio:'ignore'});
  const portFile=path.join(dir,'DevToolsActivePort');
  for(let i=0;i<200&&!fs.existsSync(portFile);i++)await sleep(50);
  const [port,wsPath]=fs.readFileSync(portFile,'utf8').trim().split('\n');
  const ws=new WebSocket('ws://127.0.0.1:'+port+wsPath);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let id=0;const pending=new Map(),handlers=[];
  ws.onmessage=m=>{const d=JSON.parse(m.data);if(d.id&&pending.has(d.id)){const p=pending.get(d.id);pending.delete(d.id);d.error?p.j(Error(d.error.message)):p.r(d.result);}else handlers.forEach(h=>h(d));};
  const send=(method,params={},sessionId)=>new Promise((r,j)=>{const n=++id;pending.set(n,{r,j});ws.send(JSON.stringify({id:n,method,params,sessionId}));});
  return {send,on:h=>handlers.push(h),close(){try{ws.close();}catch(_){}proc.kill('SIGKILL');setTimeout(()=>fs.rmSync(dir,{recursive:true,force:true}),300);}};
}
// Opens a tab whose every request is answered by `route(url, resourceType)` -> HTML string or null
// (null = blocked). Nothing reaches the network.
async function openPage(cdp,url,route){
  const {targetId}=await cdp.send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await cdp.send('Target.attachToTarget',{targetId,flatten:true});
  const s=(m,p)=>cdp.send(m,p,sessionId);
  cdp.on(d=>{if(d.sessionId!==sessionId||d.method!=='Fetch.requestPaused')return;const html=route(d.params.request.url,d.params.resourceType);
    // A request can still be in flight when its tab closes; that answer is moot, not a test failure.
    if(html!=null)s('Fetch.fulfillRequest',{requestId:d.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/html; charset=utf-8'}],body:Buffer.from(html).toString('base64')}).catch(()=>{});
    else s('Fetch.failRequest',{requestId:d.params.requestId,errorReason:'BlockedByClient'}).catch(()=>{});});
  await s('Fetch.enable',{patterns:[{urlPattern:'*'}]});await s('Page.enable');await s('Runtime.enable');
  const evaluate=async expr=>{const r=await s('Runtime.evaluate',{expression:expr,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception&&r.exceptionDetails.exception.description||r.exceptionDetails.text);return r.result.value;};
  const codes={Escape:27,Back:10009,ArrowUp:38,ArrowDown:40,ArrowLeft:37,ArrowRight:39,Enter:13};
  const key=async(name,opts={})=>{const k=name==='Back'?'':name;
    await s('Input.dispatchKeyEvent',{type:'rawKeyDown',key:k,code:k,windowsVirtualKeyCode:codes[name],nativeVirtualKeyCode:codes[name],autoRepeat:!!opts.repeat});
    await s('Input.dispatchKeyEvent',{type:'keyUp',key:k,code:k,windowsVirtualKeyCode:codes[name],nativeVirtualKeyCode:codes[name]});};
  return {send:s,evaluate,key,navigate:u=>s('Page.navigate',{url:u||url}),close:()=>cdp.send('Target.closeTarget',{targetId})};
}
module.exports={chromePath,requireChrome,launch,openPage,sleep};
