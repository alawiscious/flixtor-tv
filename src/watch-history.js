/* Read FlixTor-owned playback positions; resolve separate profile completion facts without inventing playback progress. */
var FTV_HISTORY=(function(){
  function parse(key,value){var k=/^pos:(\d+)(?::(\d+):(\d+))?$/.exec(key),v=String(value||'').split(':').map(Number);if(!k||v.length!==3||!v.every(function(n){return isFinite(n)&&n>=0;})||!v[1]||!v[2])return null;return {id:k[1],season:Number(k[2])||0,number:Number(k[3])||0,position:Math.min(v[0],v[1]),duration:v[1],timestamp:v[2],progress:Math.min(100,v[0]/v[1]*100),complete:v[0]/v[1]>=.98};}
  function records(){var out=[];try{for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);if(k&&k.indexOf('pos:')===0){var p=parse(k,localStorage.getItem(k));if(p)out.push(p);}}}catch(_){}return out.sort(function(a,b){return b.timestamp-a.timestamp;});}
  function latest(id,series){return records().filter(function(p){return p.id===String(id)&&!!p.season===!!series;})[0]||null;}
  function applyProgress(item,p){if(p){item.resume=p;item.progress=p.progress;}return item;}
  function decorateAll(items){var index=Object.create(null);records().forEach(function(p){var key=p.id+':'+String(!!p.season);if(!index[key])index[key]=p;});return items.map(function(item){var m=(item.url||'').match(/\/watch\/(tv|movie)\/(\d+)/);return applyProgress(item,m&&index[m[2]+':'+String(m[1]==='tv')]);});}
  function decorate(item){var m=(item.url||'').match(/\/watch\/(tv|movie)\/(\d+)/),p=m&&latest(m[2],m[1]==='tv');return applyProgress(item,p);}
  function label(p){return (p.season?'S'+p.season+' · E'+p.number+' · ':'')+(p.complete?'Watched':Math.floor(p.position/60)+' min watched · '+Math.ceil((p.duration-p.position)/60)+' min left');}
  function next(episodes,current){var sorted=episodes.slice().sort(function(a,b){return a.season-b.season||a.number-b.number;});for(var i=0;i<sorted.length;i++)if(sorted[i].season===current.season&&sorted[i].number===current.number)return sorted[i+1]||null;return null;}
  function episodeNumber(n){return typeof n==='number'&&isFinite(n)&&n>0&&Math.floor(n)===n;}
  // Explicit completion facts take precedence; native progress remains untouched.
  function episodeState(nativeRecord,season,number,facts){
    if(!episodeNumber(season)||!episodeNumber(number))return {watched:false,source:'none'};
    facts=facts||{};var explicit=facts.episodes&&facts.episodes[season+':'+number];
    if(explicit&&typeof explicit.watched==='boolean')return {watched:explicit.watched,source:'manual'};
    var seasons=Array.isArray(facts.completedSeasons)?facts.completedSeasons:[],through=facts.completedThrough;
    if(seasons.indexOf(season)!==-1||(through&&episodeNumber(through.season)&&episodeNumber(through.episode)&&(season<through.season||(season===through.season&&number<=through.episode))))return {watched:true,source:'manual'};
    if(nativeRecord&&nativeRecord.season===season&&nativeRecord.number===number&&nativeRecord.complete===true)return {watched:true,source:'native'};
    return {watched:false,source:'none'};
  }
  // Return the first available unwatched episode; this never creates a resume position.
  function nextUnwatched(episodes,facts){
    var sorted=episodes.filter(function(ep){return ep&&episodeNumber(ep.season)&&episodeNumber(ep.number);}).slice().sort(function(a,b){return a.season-b.season||a.number-b.number;});
    for(var i=0;i<sorted.length;i++)if(!episodeState(sorted[i].resume,sorted[i].season,sorted[i].number,facts).watched)return sorted[i];
    return null;
  }
  function loadWatching(done){var finished=false,timer=setTimeout(finish,4000);function finish(root){if(finished)return;finished=true;clearTimeout(timer);done(root||null);}function load(){try{if(typeof window.getLclsIDs!=='function'||!window.jQuery){finish();return;}window.jQuery.ajax({url:'/mylists/watched?ajax=1',type:'post',contentType:'application/json',data:window.getLclsIDs(),dataType:'html',timeout:3000,success:function(html){finish(new DOMParser().parseFromString(html,'text/html'));},error:function(){finish();}});}catch(_){finish();}}if(typeof window.hqsSyncReady==='function')window.hqsSyncReady(load);else load();}
  return {parse:parse,records:records,latest:latest,decorate:decorate,decorateAll:decorateAll,label:label,next:next,episodeState:episodeState,nextUnwatched:nextUnwatched,loadWatching:loadWatching};
}());
