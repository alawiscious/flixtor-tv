// Pairing screen and connection wording in headless Chrome, over the TV shell (/tv) with an in-page
// fake TV service (no network). The real service routes are covered by test-remote-service.cjs.
// Chrome only; the Samsung browser still needs a TV check.
'use strict';
const assert=require('node:assert/strict');
const {launch,openPage,sleep}=require('./browser-harness.cjs');
const bundle=require('./bundle.cjs').appBundle(__dirname);

const VIEWER1='ftv-netflix-'+'a'.repeat(16),VIEWER2='ftv-netflix-'+'b'.repeat(16);
const item=(n)=>({id:'flixtor:movie:'+n,title:'Pick '+n,year:2024,meta:'Drama',image:'https://img.xcdn.to/t/p/w342/p'+n+'.jpg',url:'https://flixtor.to/watch/movie/'+n+'/pick-'+n,reason:'synthetic'});
const LAN_BUNDLE={engine:'gorse',items:[item(1)],profiles:[{id:'household',name:'Household',items:[item(1)]},{id:VIEWER1,name:'Viewer One',items:[item(2)]},{id:VIEWER2,name:'Viewer Two',items:[item(3)]}]};
const REMOTE_BUNDLE={engine:'gorse',id:VIEWER1,name:'Viewer One',items:[item(4)],profiles:[{id:VIEWER1,name:'Viewer One',items:[item(4)]}]};

// Fake service inside the page: a tiny state machine answering the bridge routes the UI calls.
function fakeService(config){return `(function(){var S=${JSON.stringify(config)};window.__svc=S;S.log=[];
  function answer(method,url,body,headers){var path=url.replace(location.origin,'');S.log.push({method:method,path:path,body:body,token:headers['X-FTV-Update-Token']||''});
    if(path==='/connection')return S.supported?[200,{mode:S.paired?'remote':'lan',paired:S.paired,label:S.paired?'Remote TV':'',profiles:S.paired?[{id:${JSON.stringify(VIEWER1)},name:'Viewer One'}]:[],error:S.error||''}]:[404,{}];
    if(path==='/pair'){if(headers['X-FTV-Update-Token']!=='shell-token')return [403,{}];var code=JSON.parse(body).code;if(code==='GREATPAD'){S.paired=true;S.error='';return [200,{mode:'remote',paired:true,label:'Remote TV',profiles:[{id:${JSON.stringify(VIEWER1)},name:'Viewer One'}],error:''}];}return [401,{error:'Pairing code is wrong or expired',code:'bad-code'}];}
    if(path==='/connection/forget'){S.paired=false;S.error='';return [200,{mode:'lan',paired:false,label:'',profiles:[],error:''}];}
    if(path==='/recommendations'){if(S.paired&&S.remoteDown){S.error='unreachable';return [503,{error:'Cannot reach the recommendation server',code:'unreachable'}];}if(S.paired)return S.error==='remote-403'?[403,{error:'Connection removed',code:'revoked'}]:[200,${JSON.stringify(REMOTE_BUNDLE)}];return S.lanUp?[200,${JSON.stringify(LAN_BUNDLE)}]:[503,{error:'Start the recommendation relay on the Mac'}];}
    if(path==='/updates/healthy')return [200,{healthy:true}];
    return [404,{}];}
  function X(){this.headers={};this.status=0;this.responseText='';}
  X.prototype.open=function(m,u){this.m=m;this.u=u;};X.prototype.setRequestHeader=function(k,v){this.headers[k]=v;};
  X.prototype.send=function(b){var x=this;setTimeout(function(){var r=answer(x.m,x.u,b||'',x.headers);x.status=r[0];x.responseText=JSON.stringify(r[1]);x.onload&&x.onload();},20);};
  window.XMLHttpRequest=X;window.FTV_UPDATE_TOKEN='shell-token';try{localStorage.clear();sessionStorage.clear();}catch(_){}
}());`;}
const page=c=>'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>FlixTor TV</title></head><body><script>'+fakeService(c)+'</script><script>'+bundle.replace(/<\/script/gi,'<\\/script')+'</script></body></html>';
const SHELL='http://127.0.0.1:8773/tv#'+encodeURIComponent(JSON.stringify({path:'/home',items:[]}));

const text=p=>p.evaluate('document.getElementById("ftv").innerText');
const click=(p,label)=>p.evaluate(`(function(){var b=Array.prototype.filter.call(document.querySelectorAll('#ftv button'),function(e){return e.textContent.trim()===${JSON.stringify(label)}&&e.offsetParent!==null&&!e.disabled;}).pop();if(!b)return false;b.click();return true;}())`);
async function waitFor(p,expr,what){for(let i=0;i<100;i++){if(await p.evaluate(expr).catch(()=>false))return;await sleep(50);}throw Error('timed out waiting for '+what);}
async function type(p,code){for(const ch of code)assert(await click(p,ch),'key '+ch);}
async function open(cdp,config){const p=await openPage(cdp,SHELL,u=>u.indexOf('http://127.0.0.1:8773/tv')===0?page(config):null);await p.navigate();await waitFor(p,'!!document.querySelector("#ftv nav")','shell');await sleep(300);return p;}
async function forYou(p){await p.evaluate('(function(){var b=document.querySelector(\'#ftv nav [data-tab="For You"]\');b.click();return true;}())');await sleep(400);}

(async()=>{
  const cdp=await launch();const results=[];
  async function scenario(name,fn){try{await fn();results.push(name);console.log('  ok  '+name);}catch(e){console.log('  FAIL '+name+'\n       '+e.message.split('\n')[0]);process.exitCode=1;}}
  try{
    await scenario('older service: no pairing controls, home-network wording unchanged',async()=>{
      const p=await open(cdp,{supported:false,paired:false,lanUp:false});try{
        await forYou(p);await waitFor(p,'document.getElementById("ftv").innerText.indexOf("Recommendations are unavailable")>=0','failure');
        const t=await text(p);assert(t.includes('Keep the Mac and Gorse running'));assert(!t.includes('pairing code'));
        assert(await click(p,'Recommendations for: Choose profile'));await sleep(200);assert(!(await text(p)).includes('Connect to recommendations'));
      }finally{await p.close();}});

    await scenario('away from home: failure suggests pairing; wrong code then right code; picks switch to the paired profile only',async()=>{
      const p=await open(cdp,{supported:true,paired:false,lanUp:true});try{
        await forYou(p);await waitFor(p,'!!document.querySelector(".overlay")||document.getElementById("ftv").innerText.indexOf("Pick")>=0','LAN picks or chooser');
        // LAN bundle loaded first (household + two viewers), as on a TV that was at home.
        if(await p.evaluate('!!document.querySelector(".overlay")'))assert(await click(p,'Household'));
        await sleep(200);assert(await click(p,'Recommendations for: Household'));await sleep(200);
        let t=await text(p);assert(t.includes('Viewer Two'),'LAN chooser lists other viewers');
        assert(await click(p,'Connect to recommendations'));await waitFor(p,'document.getElementById("ftv").innerText.indexOf("8-character pairing code")>=0','code entry');
        assert.equal(await p.evaluate('document.activeElement.textContent'),'A','focus starts on the first key (remote friendly)');
        await p.key('Enter');await sleep(100);assert((await text(p)).includes('A•••-••••'),'Enter on a key types it');
        assert(await click(p,'Clear'));await type(p,'BADKEY23');assert(await click(p,'Connect'));
        await waitFor(p,'document.getElementById("ftv").innerText.indexOf("wrong or has expired")>=0','wrong-code message');
        const pairCall=await p.evaluate('window.__svc.log.filter(function(l){return l.path==="/pair";})[0]');
        assert.equal(pairCall.token,'shell-token');assert.equal(JSON.parse(pairCall.body).code,'BADKEY23');
        assert((await text(p)).includes('••••-••••'),'code cleared after a failure');
        await type(p,'GREATPAD');assert(await click(p,'Connect'));
        await waitFor(p,'!document.querySelector(".overlay")&&document.getElementById("ftv").innerText.indexOf("Pick 4")>=0','remote picks');
        t=await text(p);assert(t.includes('Recommendations for: Viewer One'));
        for(const leaked of ['Viewer Two','Household','Pick 1','Pick 3'])assert(!t.includes(leaked),'after pairing the page must not show '+leaked);
        const saved=await p.evaluate('localStorage.getItem("ftv.recommendationSnapshot.v1")||""');assert(!saved.includes('Viewer Two')&&!saved.includes('household'),'saved snapshot holds only the paired profile');
        assert(await click(p,'Recommendations for: Viewer One'));await sleep(200);t=await text(p);assert(!t.includes('Viewer Two'));assert(t.includes('Recommendation connection'));
      }finally{await p.close();}});

    await scenario('LAN down, not paired: failure text offers a pairing code',async()=>{
      const p=await open(cdp,{supported:true,paired:false,lanUp:false});try{
        await forYou(p);await waitFor(p,'document.getElementById("ftv").innerText.indexOf("Recommendations are unavailable")>=0','failure');
        assert((await text(p)).includes('Not on the home network? Connect this TV with a pairing code.'));
      }finally{await p.close();}});

    await scenario('revoked on the server: wording says removed, Pair again opens code entry; remove returns to home network',async()=>{
      const p=await open(cdp,{supported:true,paired:true,error:'remote-403',lanUp:true});try{
        await forYou(p);await waitFor(p,'document.getElementById("ftv").innerText.indexOf("connection was removed")>=0','removed wording');
        assert(await click(p,'Pair again'));await waitFor(p,'document.getElementById("ftv").innerText.indexOf("Connection removed on the server")>=0','paired status in dialog');
        assert(await click(p,'Remove connection'));await sleep(200);assert(await click(p,'Remove connection'));
        await waitFor(p,'window.__svc.paired===false','forget');await sleep(400);
        assert(await p.evaluate('window.__svc.log.some(function(l){return l.path==="/connection/forget"&&l.token==="shell-token";})'));
      }finally{await p.close();}});

    await scenario('paired, server unreachable: wording points at the TV internet, not the Mac',async()=>{
      const p=await open(cdp,{supported:true,paired:true,error:'',lanUp:false,remoteDown:true});try{
        await forYou(p);await waitFor(p,'document.getElementById("ftv").innerText.indexOf("Recommendations are unavailable")>=0','failure');
        const t=await text(p);assert(t.includes('Check this TV’s internet connection'));assert(!t.includes('Keep the Mac'));
      }finally{await p.close();}});
  }finally{cdp.close();}
  if(process.exitCode){console.log('FAIL: pairing screen browser test.');return;}
  console.log('PASS: pairing screen in Chrome ('+results.length+' scenarios: older service, wrong/right code, remote Enter, profile isolation after pairing, LAN-down hint, revoked, remove, unreachable wording). Samsung layout needs a TV check.');
})().catch(e=>{console.error(e);process.exit(1);});
