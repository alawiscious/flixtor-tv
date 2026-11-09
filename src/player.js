/* Player quality selection uses the player's offered levels, never guessed stream URLs. */
var FTV_PLAYER = (function () {
  function bestQuality(levels) {
    var best=-1,score=0;
    (levels||[]).forEach(function(level,index){
      var label=String(level.label||'');
      if(/^auto/i.test(label))return;
      var match=label.match(/(\d{3,4})p/i);
      var height=Number(level.height)||Number(match&&match[1])||(/4k/i.test(label)?2160:0);
      var value=height*1000000000+(Number(level.bitrate)||0);
      if(value>score){score=value;best=index;}
    });
    return best;
  }
  function preferHighest(player) {
    try {
      var index=bestQuality(player.getQualityLevels());
      if(index<0)return false;
      if(player.getCurrentQuality()!==index)player.setCurrentQuality(index);
      return player.getCurrentQuality()===index;
    } catch (_) {return false;}
  }
  function setSound(player,video,on){
    var changed=false;
    try{if(player&&typeof player.setMute==='function'){player.setMute(!on);if(on&&typeof player.getVolume==='function'&&player.getVolume()===0&&typeof player.setVolume==='function')player.setVolume(50);changed=true;}}catch(_){}
    try{if(video){video.muted=!on;if(on&&video.volume===0)video.volume=.5;changed=true;}}catch(_){}
    return changed;
  }
  function sourceVolume(player,video){
    try{if(player&&typeof player.getVolume==='function'){var n=Number(player.getVolume());if(isFinite(n)&&n>=0&&n<=100)return Math.round(n);}}catch(_){}
    try{if(video&&isFinite(video.volume))return Math.round(video.volume*100);}catch(_){}
    return null;
  }
  function setSourceVolume(player,video,level){
    if([50,75,100].indexOf(level)===-1)return false;
    var changed=false;
    try{if(player&&typeof player.setVolume==='function'){player.setVolume(level);changed=true;}}catch(_){}
    try{if(video){video.volume=level/100;video.muted=false;changed=true;}}catch(_){}
    if(changed)try{if(player&&typeof player.setMute==='function')player.setMute(false);}catch(_){}
    return changed;
  }
  return {sourceVolume:sourceVolume,setSourceVolume:setSourceVolume,bestQuality:bestQuality,preferHighest:preferHighest,setSound:setSound};
}());
