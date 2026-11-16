/* Read FlixTor-owned playback positions; resolve separate profile completion facts without inventing playback progress. */
var FTV_HISTORY=(function(){
  function parse(key,value){var k=/^pos:(\d+)(?::(\d+):(\d+))?$/.exec(key),v=String(value||'').split(':').map(Number);if(!k||v.length!==3||!v.every(function(n){return isFinite(n)&&n>=0;})||!v[1]||!v[2])return null;return {id:k[1],type:k[2]===undefined?'movie':'tv',season:Number(k[2])||0,number:Number(k[3])||0,position:Math.min(v[0],v[1]),duration:v[1],timestamp:v[2],progress:Math.min(100,v[0]/v[1]*100),complete:v[0]/v[1]>=.98};}
  function records(){var out=[];try{for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);if(k&&k.indexOf('pos:')===0){var p=parse(k,localStorage.getItem(k));if(p)out.push(p);}}}catch(_){}return out.sort(function(a,b){return b.timestamp-a.timestamp;});}
  function latest(id,series){return records().filter(function(p){return p.id===String(id)&&(p.type==='tv')===!!series;})[0]||null;}
  function applyProgress(item,p){if(p){item.resume=p;item.progress=p.progress;}return item;}
  function decorateAll(items){var index=Object.create(null);records().forEach(function(p){var key=p.id+':'+String(p.type==='tv');if(!index[key])index[key]=p;});return items.map(function(item){var m=(item.url||'').match(/\/watch\/(tv|movie)\/(\d+)/);return applyProgress(item,m&&index[m[2]+':'+String(m[1]==='tv')]);});}
  function decorate(item){var m=(item.url||'').match(/\/watch\/(tv|movie)\/(\d+)/),p=m&&latest(m[2],m[1]==='tv');return applyProgress(item,p);}
  function label(p){return (p.number?'S'+p.season+' · E'+p.number+' · ':'')+(p.complete?'Watched':Math.floor(p.position/60)+' min watched · '+Math.ceil((p.duration-p.position)/60)+' min left');}
  function next(episodes,current){var sorted=episodes.slice().sort(function(a,b){return a.season-b.season||a.number-b.number;});for(var i=0;i<sorted.length;i++)if(sorted[i].season===current.season&&sorted[i].number===current.number)return sorted[i+1]||null;return null;}
  function episodeNumber(n){return typeof n==='number'&&isFinite(n)&&n>0&&Math.floor(n)===n;}
  // Episode watched state, resolved here and nowhere else in the app. Explicit precedence:
  //   1. the profile's own facts (one episode, then a completed season or range)
  //   2. facts.imported: episodes the service resolved as mostly finished on a streaming import
  //   3. FlixTor's own completed position on this TV (left untouched)
  var IMPORT_SOURCES=['netflix','amazon'];
  function episodeState(nativeRecord,season,number,facts){
    if(!episodeNumber(season)||!episodeNumber(number))return {watched:false,source:'none'};
    facts=facts||{};var explicit=facts.episodes&&facts.episodes[season+':'+number];
    if(explicit&&typeof explicit.watched==='boolean')return {watched:explicit.watched,source:'manual'};
    var seasons=Array.isArray(facts.completedSeasons)?facts.completedSeasons:[],through=facts.completedThrough;
    if(seasons.indexOf(season)!==-1||(through&&episodeNumber(through.season)&&episodeNumber(through.episode)&&(season<through.season||(season===through.season&&number<=through.episode))))return {watched:true,source:'manual'};
    var imported=facts.imported&&typeof facts.imported==='object'?facts.imported:{};
    for(var i=0;i<IMPORT_SOURCES.length;i++){var bySeason=imported[IMPORT_SOURCES[i]],listed=bySeason&&typeof bySeason==='object'?bySeason[season]:null;if(Array.isArray(listed)&&listed.indexOf(number)!==-1)return {watched:true,source:IMPORT_SOURCES[i]};}
    if(nativeRecord&&nativeRecord.season===season&&nativeRecord.number===number&&nativeRecord.complete===true)return {watched:true,source:'native'};
    return {watched:false,source:'none'};
  }
  // How a title is named when the service has no catalogue id for it yet: type|title|year, or ''.
  // Must stay equal to name_key() in backend/watched.py; both tests share cases.
  function nameKey(item){
    var m=(item&&item.url||'').match(/\/watch\/(tv|movie)\//),title=String(item&&item.title||''),year=/(?:19|20)\d{2}/.exec(String(item&&item.year||''));
    try{title=title.normalize('NFKD');}catch(_){}
    title=title.toLowerCase().replace(/[^a-z0-9]/g,'');return m&&title&&year?m[1]+'|'+title+'|'+year[0]:'';
  }
  // Episode facts for one series, resolved here and nowhere else in the app: the service's facts for
  // its catalogue id; when those hold no import layer, the one the service published by name.
  function episodeFacts(item,titles,names){
    var m=(item&&item.url||'').match(/\/watch\/tv\/(\d+)/);if(!m)return null;
    var facts=titles&&typeof titles==='object'?titles['flixtor:tv:'+m[1]]:null;facts=facts&&typeof facts==='object'?facts:null;
    if(facts&&facts.imported)return facts;
    var key=nameKey(item),imported=null;
    if(key&&names&&typeof names==='object')IMPORT_SOURCES.forEach(function(service){var held=names[service],seasons=held&&typeof held==='object'&&Object.prototype.hasOwnProperty.call(held,key)?held[key]:null;if(seasons&&typeof seasons==='object'){imported=imported||{};imported[service]=seasons;}});
    if(!imported)return facts;
    var out={completedSeasons:[],completedThrough:null,episodes:{}};if(facts)Object.keys(facts).forEach(function(k){out[k]=facts[k];});out.imported=imported;return out;
  }
  // Title-level watched state, resolved here and nowhere else in the app. Explicit precedence:
  //   1. the service's resolved map (the profile's own choice, then mostly-finished streaming imports)
  //   2. names: finished imports the service published by name, for titles its catalogue does not hold yet
  //   3. FlixTor's own completed movie position on this TV
  // A series is never called watched from one finished episode.
  var TITLE_SOURCES={manual:'Marked as watched',netflix:'Watched on Netflix',amazon:'Watched on Prime Video',native:'Watched on FlixTor'};
  function titleState(item,map,names){
    var m=(item&&item.url||'').match(/\/watch\/(tv|movie)\/(\d+)/);if(!m)return {watched:false,source:'none'};
    var entry=map&&typeof map==='object'?map['flixtor:'+m[1]+':'+m[2]]:null;
    if(entry&&typeof entry==='object'&&typeof entry.watched==='boolean'&&['manual','netflix','amazon'].indexOf(entry.source)!==-1)return {watched:entry.watched,source:entry.source};
    var key=names&&typeof names==='object'?nameKey(item):'';
    if(key)for(var i=0;i<IMPORT_SOURCES.length;i++){var listed=names[IMPORT_SOURCES[i]];if(Array.isArray(listed)&&listed.indexOf(key)!==-1)return {watched:true,source:IMPORT_SOURCES[i]};}
    if(m[1]==='movie'&&item.resume&&item.resume.complete===true)return {watched:true,source:'native'};
    return {watched:false,source:'none'};
  }
  function titleLabel(state){return state&&state.watched===true&&TITLE_SOURCES[state.source]||'';}
  // Return the first available unwatched episode; this never creates a resume position.
  function nextUnwatched(episodes,facts){
    var sorted=episodes.filter(function(ep){return ep&&episodeNumber(ep.season)&&episodeNumber(ep.number);}).slice().sort(function(a,b){return a.season-b.season||a.number-b.number;});
    for(var i=0;i<sorted.length;i++)if(!episodeState(sorted[i].resume,sorted[i].season,sorted[i].number,facts).watched)return sorted[i];
    return null;
  }
  function loadWatching(done){var finished=false,timer=setTimeout(finish,4000);function finish(root){if(finished)return;finished=true;clearTimeout(timer);done(root||null);}function load(){try{if(typeof window.getLclsIDs!=='function'||!window.jQuery){finish();return;}window.jQuery.ajax({url:'/mylists/watched?ajax=1',type:'post',contentType:'application/json',data:window.getLclsIDs(),dataType:'html',timeout:3000,success:function(html){finish(new DOMParser().parseFromString(html,'text/html'));},error:function(){finish();}});}catch(_){finish();}}if(typeof window.hqsSyncReady==='function')window.hqsSyncReady(load);else load();}
  return {parse:parse,records:records,latest:latest,decorate:decorate,decorateAll:decorateAll,label:label,next:next,episodeState:episodeState,episodeFacts:episodeFacts,nameKey:nameKey,titleState:titleState,titleLabel:titleLabel,nextUnwatched:nextUnwatched,loadWatching:loadWatching};
}());
