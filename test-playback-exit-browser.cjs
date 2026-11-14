// Playback -> Back -> details lifecycle, exercised in real headless Chrome against a synthetic
// FlixTor watch page. Every request is answered locally by the DevTools Fetch domain; nothing
// contacts flixtor.to or the recommendation relay. The fake JW player is a model, not FlixTor's
// player, and Chrome is not Samsung's media stack: a pass here does NOT establish TV behavior.
//
//   node test-playback-exit-browser.cjs                 # current sources (bundle.cjs)
//   FTV_BUNDLE_FILE=tv.js node test-playback-exit-browser.cjs   # a generated bundle, e.g. 0.3.13
'use strict';
const fs=require('node:fs'),path=require('node:path');
const {launch,openPage:openRoutedPage,sleep,requireChrome}=require('./browser-harness.cjs');
const assert=require('node:assert/strict');

const root=__dirname;
const bundle=process.env.FTV_BUNDLE_FILE?fs.readFileSync(path.resolve(root,process.env.FTV_BUNDLE_FILE),'utf8'):require('./bundle.cjs').appBundle(root);
const chromePath=requireChrome();

// One second of silent 8 kHz PCM WAV, looped by the <video>, so play/pause events are real.
function silentWav(){const n=8000,b=Buffer.alloc(44+n);b.write('RIFF',0);b.writeUInt32LE(36+n,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(8000,28);b.writeUInt16LE(1,32);b.writeUInt16LE(8,34);b.write('data',36);b.writeUInt32LE(n,40);b.fill(128,44);return 'data:audio/wav;base64,'+b.toString('base64');}

const fixture=`<!doctype html><html><head><meta charset="utf-8"><title>Fixture watch page</title>
<script>
// Instrumentation installed before the module: live timers/listeners, history.back calls, errors.
(function(){
  var T=window.FIXTURE={intervals:new Set(),listeners:0,backs:0,errors:[],plays:0,pauses:0,jwPauses:0,resumeOnExternalPause:false,resumeAlways:false};
  var si=window.setInterval,ci=window.clearInterval;
  window.setInterval=function(){var id=si.apply(window,arguments);T.intervals.add(id);return id;};
  window.clearInterval=function(id){T.intervals.delete(id);return ci.call(window,id);};
  [EventTarget.prototype].forEach(function(p){var add=p.addEventListener,rem=p.removeEventListener;
    p.addEventListener=function(){if(this===document||this===window)T.listeners++;return add.apply(this,arguments);};
    p.removeEventListener=function(){if(this===document||this===window)T.listeners--;return rem.apply(this,arguments);};});
  history.back=function(){T.backs++;};
  window.addEventListener('error',function(e){T.errors.push(String(e.message));});
  window.addEventListener('unhandledrejection',function(e){var r=e.reason;if(r&&r.name==='AbortError')return;T.errors.push('rejection: '+(r&&r.message||r));});
}());
</script></head><body>
<div class="watch-header" data-href="/watch/movie/1212-twelve-twelve-twelve">12 12 12 (2012)</div>
<img alt="Poster Image" data-txt="12 12 12" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
<div class="moreless-content">Fixture synopsis.</div>
<div id="playerwrapper"><div id="player" class="jwplayer"><video id="v" loop preload="auto" src="${silentWav()}"></video></div></div>
<script>
// Minimal JW-like API over the real <video>. With resumeOnExternalPause it models a player that
// restarts whenever something other than its own API pauses it (the suspected ping-pong hazard).
(function(){
  var T=window.FIXTURE,v=document.getElementById('v'),own=false;
  v.addEventListener('play',function(){T.plays++;});
  v.addEventListener('pause',function(){T.pauses++;if(!v.getAttribute('src'))return;if(T.resumeAlways||(!own&&T.resumeOnExternalPause))setTimeout(function(){var p=v.play();if(p&&p.catch)p.catch(function(){});},0);});
  var api={getState:function(){return v.paused?'paused':'playing';},getPosition:function(){return v.currentTime;},
    play:function(){var p=v.play();if(p&&p.catch)p.catch(function(){});},
    pause:function(){T.jwPauses++;own=true;v.pause();setTimeout(function(){own=false;},0);},
    stop:function(){T.stops=(T.stops||0)+1;own=true;v.removeAttribute('src');v.load();setTimeout(function(){own=false;},0);},getQualityLevels:function(){return [{label:'Auto'},{label:'1080p',height:1080}];},getCurrentQuality:function(){return 1;},setCurrentQuality:function(){},
    getMute:function(){return v.muted;},setMute:function(m){v.muted=m;},getVolume:function(){return v.volume*100;},setVolume:function(n){v.volume=n/100;},
    getAudioTracks:function(){return [];},getCaptionsList:function(){return [{label:'Off'}];},getCurrentCaptions:function(){return 0;}};
  window.jwplayer=function(){return api;};
}());
</script>
<script>${bundle.replace(/<\/script/gi,'<\\/script')}</script>
</body></html>`;

// Every request is answered locally: the fixture for the watch document, nothing else.
async function openPage(cdp,url){
  const page=await openRoutedPage(cdp,url,(u,type)=>/^https:\/\/flixtor\.to\/watch\//.test(u)&&type==='Document'?fixture:null);
  await page.navigate();
  for(let i=0;i<100;i++){if(await page.evaluate('!!document.getElementById("ftv")&&!!document.querySelector("#ftv .overlay")').catch(()=>false))break;await sleep(50);}
  return page;
}
const URL_MOVIE='https://flixtor.to/watch/movie/1212-twelve-twelve-twelve#ftv-details';

const STATE=`(function(){var h=document.getElementById('ftv'),v=document.getElementById('v'),a=document.activeElement,F=window.FIXTURE;
  return {hostShown:!!h&&h.style.display!=='none',details:!!document.querySelector('#ftv .overlay'),cinema:document.documentElement.classList.contains('ftv-cinema'),
    focusInHost:!!h&&h.contains(a),focusText:a&&a.textContent.trim().slice(0,40),paused:v.paused,plays:F.plays,pauses:F.pauses,jwPauses:F.jwPauses,
    intervals:F.intervals.size,listeners:F.listeners,backs:F.backs,errors:F.errors.slice(),controls:!!document.getElementById('ftv-player-controls'),next:!!document.getElementById('ftv-next-episode')};}())`;
const PLAY=`(function(){var b=Array.prototype.find.call(document.querySelectorAll('#ftv .overlay button'),function(b){return /Play on FlixTor/.test(b.textContent);});b.focus();b.click();return true;}())`;

async function scenario(cdp,name,fn){const page=await openPage(cdp,URL_MOVIE);try{await fn(page);console.log('  ok  '+name);return null;}catch(e){console.log('  FAIL '+name+'\n       '+e.message.split('\n')[0]);return name;}finally{await page.close();}}

(async()=>{
  const cdp=await launch(['--autoplay-policy=no-user-gesture-required']);const failures=[];
  try{
    console.log('Bundle: '+(process.env.FTV_BUNDLE_FILE||'current sources via bundle.cjs')+' · Chrome: '+path.basename(chromePath));
    failures.push(await scenario(cdp,'movie playback -> Back -> usable details',async p=>{
      await p.evaluate(PLAY);await sleep(600);let s=await p.evaluate(STATE);
      assert(s.cinema&&!s.hostShown&&!s.paused,'playback started in cinema mode');
      await p.key('Escape');await sleep(400);s=await p.evaluate(STATE);
      assert(s.paused,'media paused');assert(!s.cinema,'cinema mode removed');assert(s.hostShown&&s.details,'details restored');
      assert(s.focusInHost,'focus on a details control, got "'+s.focusText+'"');assert(!s.controls&&!s.next,'player overlays removed');
      const before=s.focusText;await p.key('ArrowRight');await sleep(150);s=await p.evaluate(STATE);assert(s.focusInHost&&s.focusText!==before,'arrow keys still move focus');
      assert.equal(s.backs,0,'exiting playback must not navigate');assert.deepEqual(s.errors,[]);
    }));
    failures.push(await scenario(cdp,'Samsung Back keyCode 10009 exits playback',async p=>{
      await p.evaluate(PLAY);await sleep(500);await p.key('Back');await sleep(400);const s=await p.evaluate(STATE);
      assert(s.paused&&s.hostShown&&s.focusInHost&&!s.cinema,'details usable after 10009');assert.deepEqual(s.errors,[]);
    }));
    failures.push(await scenario(cdp,'held Back (auto-repeat) does not also leave the details page',async p=>{
      await p.evaluate(PLAY);await sleep(500);await p.key('Back');await p.key('Back',{repeat:true});await p.key('Back',{repeat:true});await sleep(300);
      const s=await p.evaluate(STATE);assert(s.hostShown&&s.details,'details visible');assert.equal(s.backs,0,'repeat Back must not call history.back(), got '+s.backs);
    }));
    failures.push(await scenario(cdp,'a deliberate later Back from details still navigates back',async p=>{
      await p.evaluate(PLAY);await sleep(500);await p.key('Back');await sleep(1200);await p.key('Back');await sleep(200);
      assert.equal((await p.evaluate(STATE)).backs,1,'Back from details must work after playback');
    }));
    failures.push(await scenario(cdp,'five playback/Back cycles do not accumulate timers or listeners',async p=>{
      // Warm-up cycle installs the one-time playback key listeners before the baseline.
      await p.evaluate(PLAY);await sleep(500);await p.key('Escape');await sleep(1100);const base=await p.evaluate(STATE);let s;
      for(let i=0;i<5;i++){await p.evaluate(PLAY);await sleep(500);await p.key('Escape');await sleep(1100);s=await p.evaluate(STATE);assert(s.paused&&s.focusInHost,'cycle '+(i+1)+' left usable details');}
      assert(s.intervals<=base.intervals,'live intervals grew '+base.intervals+' -> '+s.intervals);assert(s.listeners<=base.listeners,'document/window listeners grew '+base.listeners+' -> '+s.listeners);
      assert.deepEqual(s.errors,[]);
    }));
    failures.push(await scenario(cdp,'Back while player settings are open closes settings first',async p=>{
      await p.evaluate(PLAY);await sleep(500);await p.key('ArrowUp');await p.key('Enter');await sleep(150);
      assert(await p.evaluate('!!document.querySelector("#ftv-player-controls .ftv-player-panel")'),'settings panel open');
      await p.key('Escape');await sleep(200);let s=await p.evaluate(STATE);assert(!s.hostShown&&!s.paused,'first Back only closes settings');
      await p.key('Escape');await sleep(400);s=await p.evaluate(STATE);assert(s.paused&&s.hostShown&&s.focusInHost,'second Back returns to details');
    }));
    failures.push(await scenario(cdp,'Back while the player is still loading',async p=>{
      await p.evaluate(`(function(){var v=document.getElementById('v');window.FIXTURE.src=v.src;v.removeAttribute('src');v.load();return true;}())`);
      await p.evaluate(PLAY);await sleep(150);await p.key('Escape');await sleep(300);
      // The stream arrives late and the native page tries to start it.
      await p.evaluate(`(function(){var v=document.getElementById('v');v.src=window.FIXTURE.src;var x=v.play();if(x&&x.catch)x.catch(function(){});return true;}())`);await sleep(800);
      const s=await p.evaluate(STATE);assert(s.paused,'late stream must not keep playing behind details');assert(s.hostShown&&s.focusInHost,'details usable');assert.deepEqual(s.errors,[]);
    }));
    failures.push(await scenario(cdp,'player that restarts after an external pause cannot ping-pong',async p=>{
      await p.evaluate(PLAY);await sleep(500);await p.evaluate('window.FIXTURE.resumeOnExternalPause=true');
      const a=await p.evaluate(STATE);await p.key('Escape');await sleep(1500);const b=await p.evaluate(STATE);
      const plays=b.plays-a.plays;assert(plays<=6,'play events after exit must be bounded, got '+plays+' in 1.5 s');
      const c=await p.evaluate(STATE);await sleep(1000);const d=await p.evaluate(STATE);assert(d.plays-c.plays<=1,'still cycling one second later: '+(d.plays-c.plays)+' plays');
      assert(d.paused,'exit leaves the media paused: the exit must pause through the player API, not fight it');
      assert(d.hostShown&&d.focusInHost,'details usable');
    }));
    failures.push(await scenario(cdp,'player that restarts after every pause is stopped once, not fought forever',async p=>{
      await p.evaluate(PLAY);await sleep(500);await p.evaluate('window.FIXTURE.resumeAlways=true');
      const a=await p.evaluate(STATE);await p.key('Escape');await sleep(1500);const b=await p.evaluate(STATE);
      assert(b.plays-a.plays<=8,'play events after exit must be bounded, got '+(b.plays-a.plays));
      assert.equal(await p.evaluate('window.FIXTURE.stops||0'),1,'escalates to the player stop exactly once');
      assert(b.paused&&b.hostShown&&b.focusInHost,'details usable and media silent');
    }));
    failures.push(await scenario(cdp,'native autoplay on a details page is still held paused',async p=>{
      await p.evaluate(`(function(){var x=document.getElementById('v').play();if(x&&x.catch)x.catch(function(){});return true;}())`);await sleep(500);
      assert((await p.evaluate(STATE)).paused,'details page must not play behind the overlay');
    }));
    failures.push(await scenario(cdp,'play again after returning to details',async p=>{
      await p.evaluate(PLAY);await sleep(500);await p.key('Escape');await sleep(1100);await p.evaluate(PLAY);await sleep(600);
      const s=await p.evaluate(STATE);assert(!s.paused&&s.cinema&&!s.hostShown,'second playback starts normally');
    }));
  }finally{cdp.close();}
  const failed=failures.filter(Boolean);
  if(failed.length){console.log('FAIL: '+failed.length+' playback-exit browser scenario(s). Chrome only; Samsung behavior unverified.');process.exit(1);}
  console.log('PASS: playback exit in Chrome (movie, 10009, held Back, later Back, repeated cycles, settings, loading, restart model, autoplay hold, replay). Samsung behavior still requires a physical TV check.');
})().catch(e=>{console.error(e);process.exit(1);});
