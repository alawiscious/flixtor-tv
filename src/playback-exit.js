/* Playback exit lifecycle helpers. The native player stays the media owner: pausing goes through
 * its API so its own state machine agrees, and nothing here can enter an unbounded pause/play loop. */
var FTV_PLAYBACK_EXIT=(function(){
  // Run every teardown step even if an earlier one throws, so details are always restored.
  function run(steps){var failures=0;for(var i=0;i<steps.length;i++){try{steps[i]();}catch(_){failures++;}}return failures;}
  // Ask the player to pause; touch the element directly only if the player did not pause it.
  function pausePlayer(player,video){
    try{if(player&&typeof player.pause==='function'&&(typeof player.getState!=='function'||player.getState()!=='paused'))player.pause(true);}catch(_){}
    try{if(video&&!video.paused)video.pause();}catch(_){}
  }
  // Holds media paused while options.isActive() is true (details shown, no playback). A media
  // element that keeps restarting gets `limit` pauses per `windowMs`, then one options.stop()
  // escalation, then the guard stands down until reset() at the next playback exit.
  function pauseGuard(options){
    var limit=options.limit||4,windowMs=options.windowMs||2000,now=options.now||function(){return Date.now();};
    var stamps=[],escalated=false,stoodDown=false,busy=false;
    function onPlay(e){
      var target=e&&e.target;
      if(stoodDown||busy||!target||target.tagName!=='VIDEO'||!options.isActive())return;
      var t=now();stamps=stamps.filter(function(s){return t-s<windowMs;});stamps.push(t);
      busy=true;
      try{
        if(stamps.length<=limit)options.pause(target);
        else if(!escalated){escalated=true;if(options.stop)options.stop(target);}
        else stoodDown=true;
      }catch(_){}finally{busy=false;}
    }
    return {onPlay:onPlay,reset:function(){stamps=[];escalated=false;stoodDown=false;},state:function(){return {recent:stamps.length,escalated:escalated,stoodDown:stoodDown};}};
  }
  return {run:run,pausePlayer:pausePlayer,pauseGuard:pauseGuard};
}());
