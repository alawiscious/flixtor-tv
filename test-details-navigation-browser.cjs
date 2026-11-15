// Details page focus and "More like this" history, in headless Chrome over synthetic FlixTor watch
// pages (every request answered locally). Back-forward cache is disabled so Back really reloads the
// previous page, as a TV may. Chrome only; Samsung behavior still needs a TV check.
'use strict';
const assert=require('node:assert/strict');
const {launch,openPage,sleep}=require('./browser-harness.cjs');
const bundle=require('./bundle.cjs').appBundle(__dirname);

const TITLES={1:'Title Alpha',2:'Title Bravo',3:'Title Charlie'};
const slug=n=>'/watch/movie/'+n+'-'+TITLES[n].toLowerCase().replace(/ /g,'-');
function watchPage(n){
  const related=Object.keys(TITLES).filter(k=>k!==String(n)).map(k=>`<div class="flip"><a href="${slug(k)}">${TITLES[k]}</a><div class="front"><img alt="${TITLES[k]}" src="https://img.xcdn.to/t/p/w342/p${k}.jpg"><div class="card-footer">${TITLES[k]}</div></div><span class="genres">Action</span></div>`).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><title>${TITLES[n]}</title></head><body>
<div class="watch-header" data-href="${slug(n)}">${TITLES[n]} (2023)</div>
<img alt="Poster Image" data-txt="${TITLES[n]}" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
<div class="moreless-content">Synthetic synopsis.</div>
<div id="playerwrapper"><div id="player"></div></div>
<a id="native-link" href="#native">native control</a>
<div class="related">${related}</div>
<script>window.jwplayer=function(){return {getState:function(){return 'idle';},pause:function(){},play:function(){},stop:function(){}};};</script>
<script>${bundle.replace(/<\/script/gi,'<\\/script')}</script></body></html>`;
}
const route=u=>{const m=/^https:\/\/flixtor\.to\/watch\/movie\/(\d)-/.exec(u);return m&&TITLES[m[1]]?watchPage(Number(m[1])):null;};
const details=n=>'https://flixtor.to'+slug(n)+'#ftv-details='+encodeURIComponent(JSON.stringify({profileId:'household',titles:{}}));
const active='(function(){var a=document.activeElement;return a?(a.textContent||a.id||a.tagName).trim():null;}())';
async function waitFor(p,expr,what){for(let i=0;i<120;i++){if(await p.evaluate(expr).catch(()=>false))return;await sleep(50);}throw Error('timed out waiting for '+what+' (focus: '+(await p.evaluate(active).catch(()=>'?'))+'; state: '+(await p.evaluate(STATE).catch(()=>'?'))+')');}
const STATE='JSON.stringify({hash:location.hash.slice(0,16),path:location.pathname,h1:Array.prototype.map.call(document.querySelectorAll("#ftv h1"),function(h){return h.textContent;}),cards:Array.prototype.map.call(document.querySelectorAll("#ftv .card"),function(c){return c.getAttribute("aria-label");})})';
const hasDetails='!!document.querySelector("#ftv .overlay .actions .primary")';
// Scoped to the details overlay: the Home hero behind it has its own More like this button.
const clickText=(p,t)=>p.evaluate(`(function(){var b=Array.prototype.filter.call(document.querySelectorAll('#ftv .overlay button'),function(e){return e.textContent.trim()===${JSON.stringify(t)};})[0];if(!b)return false;b.click();return true;}())`);

(async()=>{
  const cdp=await launch(['--disable-features=BackForwardCache']);let failures=0;
  async function scenario(name,fn){const p=await openPage(cdp,details(1),route);try{await fn(p);console.log('  ok  '+name);}catch(e){failures++;console.log('  FAIL '+name+'\n       '+e.message.split('\n')[0]);}finally{await p.close();}}
  try{
    await scenario('focus stolen by the native page returns to Play',async p=>{
      await p.navigate();await waitFor(p,hasDetails,'details');await sleep(200);
      assert.equal(await p.evaluate(active),'▶ Play on FlixTor');
      await p.evaluate('document.getElementById("native-link").focus()');await sleep(150);
      assert.equal(await p.evaluate(active),'▶ Play on FlixTor','focus moved to a native element');
      await p.evaluate('document.activeElement.blur()');await sleep(150);
      assert.equal(await p.evaluate(active),'▶ Play on FlixTor','focus dropped to the page body');
    });
    await scenario('arrow key after focus loss continues from Play, not the Back button',async p=>{
      await p.navigate();await waitFor(p,hasDetails,'details');await sleep(200);
      // Steal focus without giving the guard a chance (as a native script would mid-keypress).
      await p.evaluate('(function(){var n=document.getElementById("native-link");n.focus();return true;}())');
      await p.key('ArrowRight');await sleep(150);
      const now=await p.evaluate(active);assert.notEqual(now,'← Back');assert(/My List/.test(now)||now==='▶ Play on FlixTor','focus is in the actions row: '+now);
    });
    await scenario('More like this → another title → Back returns to the More like this list',async p=>{
      await p.navigate();await waitFor(p,hasDetails,'details');
      assert(await clickText(p,'More like this'));await waitFor(p,'document.querySelector("#ftv main h1")&&/More like Title Alpha/.test(document.querySelector("#ftv main h1").textContent)','similar list');
      assert(/^#ftv-similar=/.test(await p.evaluate('location.hash')),'similar list is recorded in this history entry');
      await p.evaluate('(function(){var c=document.querySelector(\'#ftv main .card[aria-label="Title Bravo"]\');c.focus();return true;}())');await p.key('Enter');
      await waitFor(p,'location.pathname.indexOf("/watch/movie/2-")===0&&'+hasDetails,'Bravo details');
      await p.key('Escape');
      await waitFor(p,'location.pathname.indexOf("/watch/movie/1-")===0&&!!document.querySelector("#ftv main h1")&&/More like Title Alpha/.test(document.querySelector("#ftv main h1").textContent)','back on the similar list');
      assert(!(await p.evaluate(hasDetails)),'the list, not Alpha details, is shown');
      // Back from the list returns to Alpha details on the same page and restores the entry.
      await p.key('Escape');await waitFor(p,hasDetails,'Alpha details');
      assert(/^#ftv-details=/.test(await p.evaluate('location.hash')),'details recorded again');
      assert.equal(await p.evaluate(active),'▶ Play on FlixTor');
    });
  }finally{cdp.close();}
  if(failures){console.log('FAIL: '+failures+' details navigation scenario(s).');process.exit(1);}
  console.log('PASS: details focus guard (native focus theft, blur, arrow after loss) and More like this history (list restored on Back, details restored after). Chrome only; Samsung behavior needs a TV check.');
})().catch(e=>{console.error(e);process.exit(1);});
