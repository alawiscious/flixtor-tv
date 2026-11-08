/* Samsung requires explicit screensaver suppression for custom HTML playback.
 * Restore protection on pause, exit, hidden app, errors, or a long stalled frame. */
var FTV_PLAYBACK_POWER=(function(){
  function attach(parent,getPlayer){
    var stopped=false,disposed=false,desired=false,off=false,pending=false,wake=null,lastPosition=null,lastProgress=Date.now(),lastApply=0;
    var events=['play','playing','pause','ended','emptied','error','timeupdate'];
    function mark(value){parent.setAttribute('data-ftv-screen-awake',value);}
    function apply(playing){
      desired=playing;
      var common=window.webapis&&window.webapis.appcommon;
      if(common&&typeof common.setScreenSaver==='function'){
        if(pending||playing===off&&(!playing||Date.now()-lastApply<30000))return;
        pending=true;
        try{var states=common.AppCommonScreenSaverState||{SCREEN_SAVER_OFF:0,SCREEN_SAVER_ON:1};
          common.setScreenSaver(playing?states.SCREEN_SAVER_OFF:states.SCREEN_SAVER_ON,function(){pending=false;off=playing;lastApply=Date.now();mark(playing?'samsung-off':'samsung-on');if(off!==desired)apply(desired);},function(){pending=false;mark('samsung-error');});
        }catch(_){pending=false;mark('samsung-error');}
        return;
      }
      if(!playing){off=false;if(wake){wake.release();wake=null;}mark('released');return;}
      if(wake||pending)return;
      if(navigator.wakeLock&&typeof navigator.wakeLock.request==='function'){
        pending=true;navigator.wakeLock.request('screen').then(function(lock){pending=false;if(stopped||document.hidden||!desired){lock.release();return;}wake=lock;off=true;mark('browser-lock');lock.addEventListener('release',function(){if(wake===lock){wake=null;off=false;}});},function(){pending=false;mark('browser-error');});
      }else mark('unavailable');
    }
    function update(){
      if(stopped)return;
      var video=parent.querySelector('video'),playing=false,position=null;
      if(video){playing=!video.paused&&!video.ended&&!video.error;position=video.currentTime;}
      else try{var player=getPlayer(),state=player&&player.getState();playing=state==='playing'||state==='buffering';position=player&&player.getPosition();}catch(_){}
      if(!playing){lastPosition=null;lastProgress=Date.now();}
      else if(position!==lastPosition){lastPosition=position;lastProgress=Date.now();}
      apply(playing&&!document.hidden&&Date.now()-lastProgress<45000);
    }
    function event(e){if(parent.contains(e.target))update();}
    function exit(){stopped=true;apply(false);}
    function resume(){if(!disposed){stopped=false;lastProgress=Date.now();update();}}
    events.forEach(function(name){document.addEventListener(name,event,true);});
    document.addEventListener('visibilitychange',update);window.addEventListener('pageshow',resume);window.addEventListener('pagehide',exit);window.addEventListener('beforeunload',exit);
    var timer=setInterval(update,1000);update();
    return {destroy:function(){disposed=true;stopped=true;clearInterval(timer);events.forEach(function(name){document.removeEventListener(name,event,true);});document.removeEventListener('visibilitychange',update);window.removeEventListener('pageshow',resume);window.removeEventListener('pagehide',exit);window.removeEventListener('beforeunload',exit);apply(false);},update:update};
  }
  return {attach:attach};
}());
