// "Seen it? Rate it" on the details screen, in headless Chrome over a synthetic FlixTor watch page with
// an in-page fake bridge (no network). The service side is covered by test-remote-service.cjs.
'use strict';
const assert=require('node:assert/strict');
const {launch,openPage,sleep}=require('./browser-harness.cjs');
const bundle=require('./bundle.cjs').appBundle(__dirname);

const PROFILE='ftv-netflix-'+'a'.repeat(16);
function page(mode){return `<!doctype html><html><head><meta charset="utf-8"><title>Watch</title></head><body>
<div class="watch-header" data-href="/watch/movie/603692-john-wick-chapter-4">John Wick: Chapter 4 (2023)</div>
<img alt="Poster Image" data-txt="John Wick: Chapter 4" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
<div class="moreless-content">Synthetic synopsis.</div><div id="playerwrapper"><div id="player"></div></div>
<script>window.jwplayer=function(){return {getState:function(){return 'idle';},pause:function(){},play:function(){},stop:function(){}};};
window.FTV_BRIDGE_ORIGIN='http://127.0.0.1:8773';window.__sent=[];
(function(){var mode=${JSON.stringify(mode)};function X(){this.h={};}X.prototype.open=function(m,u){this.m=m;this.u=u;};X.prototype.setRequestHeader=function(k,v){this.h[k]=v;};
X.prototype.send=function(b){var x=this;window.__sent.push({method:x.m,url:x.u,body:JSON.parse(b||'null'),type:x.h['Content-Type']});setTimeout(function(){if(mode==='old-service'){x.status=0;x.onerror&&x.onerror();return;}x.status=200;x.responseText='{"saved":true}';x.onload();},20);};window.XMLHttpRequest=X;}());</script>
<script>${bundle.replace(/<\/script/gi,'<\\/script')}</script></body></html>`;}
function url(ratings){const ctx={profileId:PROFILE,titles:{}};if(ratings)ctx.ratings=ratings;return 'https://flixtor.to/watch/movie/603692-john-wick-chapter-4#ftv-details='+encodeURIComponent(JSON.stringify(ctx));}
const text=p=>p.evaluate('document.querySelector("#ftv .overlay").innerText');
const click=(p,label)=>p.evaluate(`(function(){var b=Array.prototype.filter.call(document.querySelectorAll('#ftv .overlay .rating-row button'),function(e){return e.textContent===${JSON.stringify(label)};})[0];if(!b)return false;b.click();return true;}())`);
const chosen=p=>p.evaluate('Array.prototype.filter.call(document.querySelectorAll("#ftv .rating-row button"),function(b){return b.getAttribute("aria-pressed")==="true";}).map(function(b){return b.textContent;})');
async function waitFor(p,expr,what){for(let i=0;i<100;i++){if(await p.evaluate(expr).catch(()=>false))return;await sleep(50);}throw Error('timed out waiting for '+what);}

(async()=>{
  const cdp=await launch();let failures=0;
  async function scenario(name,mode,target,fn){const p=await openPage(cdp,target,u=>u.indexOf('https://flixtor.to/watch/movie/603692-')===0?page(mode):null);try{await p.navigate();await waitFor(p,'!!document.querySelector("#ftv .overlay .rating-row")','rating row');await fn(p);console.log('  ok  '+name);}catch(e){failures++;console.log('  FAIL '+name+'\n       '+e.message.split('\n')[0]);}finally{await p.close();}}
  try{
    await scenario('rate, change, clear from the details screen; Play keeps focus','ok',url(),async p=>{
      assert.equal(await p.evaluate('document.activeElement.textContent'),'▶ Play on FlixTor','the rating row does not take initial focus');
      assert.deepEqual(await chosen(p),[]);assert((await text(p)).includes('Seen it? Rate it'));
      assert(await click(p,'Loved it'));await waitFor(p,'/Saved: Loved it/.test(document.querySelector("#ftv .rating-row").innerText)','saved');
      let sent=await p.evaluate('window.__sent[0]');assert.equal(sent.url,'http://127.0.0.1:8773/feedback');assert.equal(sent.type,'application/json');
      assert.deepEqual(sent.body,{profileId:PROFILE,itemId:'flixtor:movie:603692',rating:'love'},'only profile, title and rating are sent');
      assert.deepEqual(await chosen(p),['Loved it']);
      assert(await click(p,'Hated it'));await waitFor(p,'/Saved: Hated it/.test(document.querySelector("#ftv .rating-row").innerText)','changed');assert.deepEqual(await chosen(p),['Hated it']);
      assert(await click(p,'Hated it'));await waitFor(p,'/Rating cleared/.test(document.querySelector("#ftv .rating-row").innerText)','cleared');
      sent=await p.evaluate('window.__sent[2]');assert.strictEqual(sent.body.rating,null);assert.deepEqual(await chosen(p),[]);
    });
    await scenario('a rating known from For You is preselected (keyed by title id)','ok',url({'flixtor:movie:603692':'like','flixtor:movie:1':'hate'}),async p=>{
      assert.deepEqual(await chosen(p),['Liked it']);
    });
    await scenario('older TV service: clear message, nothing marked','old-service',url(),async p=>{
      assert(await click(p,'Liked it'));await waitFor(p,'/Re-add the FlixTor TV module/.test(document.querySelector("#ftv .rating-row").innerText)','re-add message');
      assert.deepEqual(await chosen(p),[]);
    });
  }finally{cdp.close();}
  if(failures){console.log('FAIL: '+failures+' rating scenario(s).');process.exit(1);}
  console.log('PASS: details-screen ratings in Chrome (rate/change/clear, minimal payload, initial focus kept, preselected known rating, older-service message). Samsung behavior needs a TV check.');
})().catch(e=>{console.error(e);process.exit(1);});
