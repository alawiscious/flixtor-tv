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
  return {bestQuality:bestQuality,preferHighest:preferHighest};
}());
