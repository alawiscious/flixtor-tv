// "Seen it? Rate it" on the details screen, in headless Chrome. The synthetic FlixTor watch page carries
// FlixTor's real CSP (connect-src 'self' *.xcdn.to), which blocks direct requests to the TV service, so
// the rating must make a round trip through the TV shell (127.0.0.1:8773/tv). The shell's /feedback call
// is answered by an in-page fake. Nothing reaches the network. Chrome only; Samsung needs a TV check.
'use strict';
const assert=require('node:assert/strict');
const {launch,openPage,sleep}=require('./browser-harness.cjs');
const bundle=require('./bundle.cjs').appBundle(__dirname).replace(/<\/script/gi,'<\\/script');

const PROFILE='ftv-netflix-'+'a'.repeat(16),WATCH='https://flixtor.to/watch/movie/603692-john-wick-chapter-4';
const CSP="default-src 'self' blob:; connect-src 'self' *.xcdn.to; img-src 'self' img.xcdn.to image.tmdb.org data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'";
const watchPage=`<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}"><title>Watch</title></head><body>
<div class="watch-header" data-href="/watch/movie/603692-john-wick-chapter-4">John Wick: Chapter 4 (2023)</div>
<img alt="Poster Image" data-txt="John Wick: Chapter 4" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
<div class="moreless-content">Synthetic synopsis.</div><div id="playerwrapper"><div id="player"></div></div>
<script>window.jwplayer=function(){return {getState:function(){return 'idle';},pause:function(){},play:function(){},stop:function(){}};};window.FTV_BRIDGE_ORIGIN='http://127.0.0.1:8773';
// Prove the CSP is live: a direct request to the TV service must be blocked here.
window.__directBlocked=null;try{var x=new XMLHttpRequest();x.open('POST','http://127.0.0.1:8773/feedback');x.onerror=function(){window.__directBlocked=true;};x.onload=function(){window.__directBlocked=false;};x.send('{}');}catch(e){window.__directBlocked=true;}</script>
<script>${bundle}</script></body></html>`;
// The TV shell (same origin as the TV service): fake /feedback + /updates answers, recorded in localStorage.
function shellPage(mode){return `<!doctype html><html><head><meta charset="utf-8"><title>FlixTor TV</title></head><body><script>
window.FTV_UPDATE_TOKEN='shell-token';(function(){var mode=${JSON.stringify(mode)};function X(){this.h={};}X.prototype.open=function(m,u){this.m=m;this.u=u;};X.prototype.setRequestHeader=function(k,v){this.h[k]=v;};
X.prototype.send=function(b){var x=this;var key='sent-'+mode,log=JSON.parse(localStorage.getItem(key)||'[]');log.push({url:x.u,body:JSON.parse(b||'null')});localStorage.setItem(key,JSON.stringify(log));
setTimeout(function(){var ok=/\\/updates\\//.test(x.u)||mode!=='down';x.status=ok?200:503;x.responseText=/\\/updates\\//.test(x.u)?'{"healthy":true}':ok?'{"saved":true,"state":{}}':'{"error":"down"}';x.onload();},30);};window.XMLHttpRequest=X;}());
</script><script>${bundle}</script></body></html>`;}
const details=ctx=>WATCH+'#ftv-details='+encodeURIComponent(JSON.stringify(Object.assign({profileId:PROFILE,titles:{}},ctx||{})));
const status='(document.querySelector("#ftv .rating-row [role=status]")||{}).textContent||""';
const chosen=p=>p.evaluate('Array.prototype.filter.call(document.querySelectorAll("#ftv .rating-row button"),function(b){return b.getAttribute("aria-pressed")==="true";}).map(function(b){return b.textContent;})');
const click=(p,label)=>p.evaluate(`(function(){var b=Array.prototype.filter.call(document.querySelectorAll('#ftv .overlay .rating-row button'),function(e){return e.textContent===${JSON.stringify(label)};})[0];if(!b)return false;b.click();return true;}())`);
async function waitFor(p,expr,what){for(let i=0;i<160;i++){if(await p.evaluate(expr).catch(()=>false))return;await sleep(50);}throw Error('timed out waiting for '+what+' at '+(await p.evaluate('location.href.slice(0,60)').catch(()=>'?')));}
const onDetails='location.origin==="https://flixtor.to"&&!!document.querySelector("#ftv .overlay .rating-row")';

(async()=>{
  const cdp=await launch();let failures=0;
  async function scenario(name,mode,start,fn){
    const p=await openPage(cdp,start,u=>u.indexOf(WATCH)===0?watchPage:u.indexOf('http://127.0.0.1:8773/tv')===0?shellPage(mode):null);
    try{await p.navigate();await waitFor(p,onDetails,'details');await fn(p);console.log('  ok  '+name);}catch(e){failures++;console.log('  FAIL '+name+'\n       '+e.message.split('\n')[0]);}finally{await p.close();}}
  try{
    await scenario('under FlixTor CSP: rate → shell saves → back on the same details, saved and focused','ok',details(),async p=>{
      await waitFor(p,'window.__directBlocked!==null','CSP probe');assert.equal(await p.evaluate('window.__directBlocked'),true,'direct requests to the TV service are blocked by the CSP (as on the TV)');
      assert.equal(await p.evaluate('document.activeElement.textContent'),'▶ Play on FlixTor');
      const before=await p.evaluate('history.length');
      assert(await click(p,'Loved it'));
      await waitFor(p,onDetails+'&&/Saved: Loved it/.test('+status+')','return with saved status');
      assert.deepEqual(await chosen(p),['Loved it']);assert.equal(await p.evaluate('document.activeElement.textContent'),'Loved it','focus stays on the rating');
      assert.equal(await p.evaluate('history.length'),before,'round trip adds no history entries, so Back is unchanged');
      // The shell's saved request (read on the shell origin via a fresh tab of the same profile is not possible; check the URL trail instead).
      assert(/#ftv-details=/.test(await p.evaluate('location.hash')));
      assert(await click(p,'Loved it'));await waitFor(p,onDetails+'&&/Rating cleared/.test('+status+')','cleared');assert.deepEqual(await chosen(p),[]);
    });
    await scenario('server unavailable: back on details with the previous rating and an error','down',details({ratings:{'flixtor:movie:603692':'like'}}),async p=>{
      assert.deepEqual(await chosen(p),['Liked it']);
      assert(await click(p,'Hated it'));
      await waitFor(p,onDetails+'&&/Could not save your rating/.test('+status+')','error status');
      assert.deepEqual(await chosen(p),['Liked it'],'previous rating kept');
    });
    await scenario('a shell link with an invalid rating saves nothing and goes back','invalid',details(),async p=>{
      await p.evaluate(`location.assign('http://127.0.0.1:8773/tv#'+encodeURIComponent(JSON.stringify({path:'/home',rate:{profileId:'household',itemId:'flixtor:movie:1',rating:'meh',url:'https://evil.example/watch/movie/1'}})))`);
      await waitFor(p,'location.origin==="http://127.0.0.1:8773"&&/could not be saved/.test(document.body.textContent)','invalid notice');
      assert.equal(await p.evaluate('JSON.parse(localStorage.getItem("sent-invalid")||"[]").filter(function(s){return /feedback/.test(s.url);}).length'),0,'no feedback request');
      await waitFor(p,onDetails,'went back');
    });
  }finally{cdp.close();}
  if(failures){console.log('FAIL: '+failures+' rating scenario(s).');process.exit(1);}
  console.log('PASS: details-screen ratings under FlixTor\'s CSP via the TV shell round trip (save, clear, failure keeps previous, invalid link rejected, no extra history, focus kept). Samsung behavior needs a TV check.');
})().catch(e=>{console.error(e);process.exit(1);});
