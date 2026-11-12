/* TV-origin display snapshot only. Never writes FlixTor playback progress or queues feedback. */
var FTV_RECOMMEND_CACHE=(function(){
  'use strict';
  var key='ftv.recommendationSnapshot.v1',limit=1048576;
  function text(value,max){return typeof value==='string'?value.slice(0,max):'';}
  function object(value){return value&&typeof value==='object'&&!Array.isArray(value);}
  function profile(value){return typeof value==='string'&&/^(household|ftv-netflix-[a-f0-9]{16})$/.test(value);}
  function integer(value,min,max){return typeof value==='number'&&isFinite(value)&&Math.floor(value)===value&&value>=min&&value<=max;}
  function address(value,image){try{var u=new URL(value);if(u.protocol!=='https:'||u.username||u.password)return '';if(image)return ['img.xcdn.to','image.tmdb.org'].indexOf(u.hostname)!==-1?u.origin+u.pathname:'';return u.origin==='https://flixtor.to'&&/^\/watch\/(tv|movie)\/[0-9]{1,18}(?:\/|$)/.test(u.pathname)?u.origin+u.pathname:'';}catch(_){return '';}}
  function feedback(value){var out={};if(!object(value))return out;if(['like','dislike','clear'].indexOf(value.preference)!==-1)out.preference=value.preference;if(value.watched===null||typeof value.watched==='boolean')out.watched=value.watched;return out;}
  function progress(value){var out={};if(!object(value))return out;Object.keys(value).slice(0,500).forEach(function(id){
    var f=value[id];if(!/^flixtor:tv:[0-9]{1,18}$/.test(id)||!object(f))return;
    var clean={completedSeasons:[],completedThrough:null,episodes:{}},seen={};
    if(Array.isArray(f.completedSeasons))f.completedSeasons.slice(0,100).forEach(function(n){if(integer(n,0,999)&&!seen[n]){clean.completedSeasons.push(n);seen[n]=true;}});
    var through=f.completedThrough;if(object(through)&&integer(through.season,0,999)&&integer(through.episode,1,9999))clean.completedThrough={season:through.season,episode:through.episode};
    if(object(f.episodes))Object.keys(f.episodes).slice(0,1000).forEach(function(k){var m=/^(\d{1,3}):(\d{1,4})$/.exec(k),v=f.episodes[k];if(m&&integer(Number(m[1]),0,999)&&integer(Number(m[2]),1,9999)&&object(v)&&typeof v.watched==='boolean')clean.episodes[Number(m[1])+':'+Number(m[2])]={watched:v.watched};});
    if(f.source==='explicit_user')clean.source=f.source;if(typeof f.updatedAt==='string')clean.updatedAt=text(f.updatedAt,64);out[id]=clean;
  });return out;}
  function pack(value,defaultId){if(!object(value)||(value.engine!==undefined&&value.engine!=='gorse'))return null;var id=value.id===undefined?defaultId:value.id;if(!profile(id)||!Array.isArray(value.items))return null;
    var out={engine:'gorse',id:id,name:text(value.name,100),scope:text(value.scope,200),model:text(value.model,200),seedCount:integer(value.seedCount,0,10000000)?value.seedCount:0,catalogueCount:integer(value.catalogueCount,0,10000000)?value.catalogueCount:0,generatedAt:text(value.generatedAt,64),cacheStatus:text(value.cacheStatus,32),stale:value.stale===true,items:[],episodeProgress:progress(value.episodeProgress)},seen={};
    value.items.slice(0,100).forEach(function(item){if(!object(item))return;var url=address(item.url,false),image=address(item.image,true),title=text(item.title,300),m=url.match(/\/watch\/(tv|movie)\/(\d+)/),ident=m?'flixtor:'+m[1]+':'+m[2]:'';if(!url||!image||!title||seen[ident])return;seen[ident]=true;out.items.push({id:ident,title:title,year:text(String(item.year||''),16),meta:text(item.meta,500),image:image,url:url,reason:text(item.reason,1000),rating:text(String(item.rating||''),16),feedback:feedback(item.feedback)});});return out;}
  function sanitize(value){if(!object(value)||value.engine!=='gorse')return null;var out=pack(value,'household');if(!out)return null;if(Array.isArray(value.profiles)){var seen={};out.profiles=[];value.profiles.slice(0,21).forEach(function(p){var clean=pack(p,null);if(clean&&!seen[clean.id]){seen[clean.id]=true;out.profiles.push(clean);}});}return out;}
  function save(bundle){try{var data=sanitize(bundle);if(!data)return false;var raw=JSON.stringify({schema:1,savedAt:Date.now(),data:data});if(raw.length*2>limit)return false;localStorage.setItem(key,raw);return true;}catch(_){return false;}}
  function load(){try{var raw=localStorage.getItem(key);if(typeof raw!=='string'||raw.length*2>limit)return null;var value=JSON.parse(raw);if(!object(value)||value.schema!==1||typeof value.savedAt!=='number'||!isFinite(value.savedAt)||value.savedAt<=0)return null;var data=sanitize(value.data);return data?{savedAt:value.savedAt,data:data}:null;}catch(_){return null;}}
  return {load:load,save:save};
}());
