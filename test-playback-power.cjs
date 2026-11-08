const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/src/playback-power.js','utf8');
function fixture({delayed=false,absent=false}={}){
  let now=0,tick;const handlers={},windows={},calls=[],pending=[],attrs={};
  const video={paused:true,ended:false,error:null,currentTime:0};
  const parent={querySelector:()=>video,contains:el=>el===video,setAttribute:(k,v)=>attrs[k]=v};
  const document={hidden:false,addEventListener:(n,fn)=>handlers[n]=fn,removeEventListener:n=>delete handlers[n]};
  const window={addEventListener:(n,fn)=>windows[n]=fn,removeEventListener:n=>delete windows[n]};
  if(!absent)window.webapis={appcommon:{AppCommonScreenSaverState:{SCREEN_SAVER_OFF:0,SCREEN_SAVER_ON:1},setScreenSaver:(value,success)=>{calls.push(value);if(delayed)pending.push(success);else success();}}};
  const context={document,window,navigator:{},Date:{now:()=>now},setInterval:fn=>{tick=fn;return 1;},clearInterval:()=>{tick=null;}};
  vm.createContext(context);vm.runInContext(source,context);
  const control=context.FTV_PLAYBACK_POWER.attach(parent,()=>null);
  return {video,document,handlers,windows,calls,pending,attrs,control,advance:ms=>{now+=ms;tick();},event:name=>handlers[name]({target:video})};
}
{
  const f=fixture();assert.deepEqual(f.calls,[]);
  f.video.paused=false;f.event('playing');assert.deepEqual(f.calls,[0]);
  f.video.paused=true;f.event('pause');assert.deepEqual(f.calls,[0,1]);
  f.video.paused=false;f.video.currentTime=4;f.event('playing');assert.equal(f.calls.at(-1),0);
  f.document.hidden=true;f.handlers.visibilitychange();assert.equal(f.calls.at(-1),1);
  f.document.hidden=false;f.handlers.visibilitychange();assert.equal(f.calls.at(-1),0);
  f.video.ended=true;f.event('ended');assert.equal(f.calls.at(-1),1);
  f.video.ended=false;f.event('playing');f.control.destroy();assert.equal(f.calls.at(-1),1);
  assert.equal(Object.keys(f.handlers).length,0);assert.equal(Object.keys(f.windows).length,0);
}
{
  const f=fixture();f.video.paused=false;f.event('playing');f.advance(46000);assert.equal(f.calls.at(-1),1,'long frozen frame restores screen protection');
  f.video.currentTime=10;f.event('timeupdate');assert.equal(f.calls.at(-1),0,'real progress resumes suppression');
  f.windows.pagehide();assert.equal(f.calls.at(-1),1);f.windows.pageshow();assert.equal(f.calls.at(-1),0);
  f.control.destroy();
}
{
  const f=fixture({delayed:true});f.video.paused=false;f.event('playing');f.video.paused=true;f.event('pause');
  f.pending.shift()();assert.deepEqual(f.calls,[0,1],'pause during pending OFF must restore ON after callback');
  f.pending.shift()();f.control.destroy();
}
{
  const f=fixture({absent:true});f.video.paused=false;f.event('playing');assert.equal(f.attrs['data-ftv-screen-awake'],'unavailable');f.control.destroy();
}
console.log('PASS: Samsung play/pause/end/visibility, exit/restore, frozen playback, asynchronous pause race, unavailable APIs and cleanup.');
