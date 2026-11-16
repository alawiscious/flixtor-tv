// Watched state from the service's resolved map (own choice, then streaming imports), in headless Chrome.
// 1. TV shell: catalogue cards read the map from the saved recommendation snapshot and badge watched titles.
// 2. FlixTor details page (real CSP, so no service calls): the entry arrives in the navigation context.
// Synthetic titles only; nothing reaches the network. Chrome only; Samsung needs a TV check.
'use strict';
const assert=require('node:assert/strict');
const {launch,openPage,sleep}=require('./browser-harness.cjs');
const bundle=require('./bundle.cjs').appBundle(__dirname).replace(/<\/script/gi,'<\\/script');

const PROFILE='household',SHELL='http://127.0.0.1:8773/tv';
const film=(id,title,extra)=>Object.assign({title,url:'https://flixtor.to/watch/movie/'+id+'/'+title.toLowerCase().replace(/[^a-z]+/g,'-'),image:'https://img.xcdn.to/t/p/w300/abc'+id+'.jpg',year:'2020',meta:'Drama'},extra||{});
const ITEMS=[film(101,'Netflix Film'),film(102,'Prime Film'),film(103,'Own Choice'),film(104,'Marked Unwatched',{resume:{id:'104',type:'movie',season:0,number:0,position:100,duration:100,timestamp:1,progress:100,complete:true}}),
  film(105,'Finished Here',{resume:{id:'105',type:'movie',season:0,number:0,position:100,duration:100,timestamp:1,progress:100,complete:true}}),film(106,'Never Seen'),film(107,'Bad Entry'),
  film(108,'Named Film'),film(109,'Named Film',{year:'1999'}),{title:'Imported Show',url:'https://flixtor.to/watch/tv/201/imported-show',image:'https://img.xcdn.to/t/p/w300/abc201.jpg',year:'2020',meta:'Drama'}];
const WATCHED={'flixtor:movie:101':{watched:true,source:'netflix'},'flixtor:movie:102':{watched:true,source:'amazon'},'flixtor:movie:103':{watched:true,source:'manual'},
  'flixtor:movie:104':{watched:false,source:'manual'},'flixtor:movie:107':{watched:true,source:'<b>elsewhere</b>'},'history:imdb:tt1':{watched:true,source:'netflix'}};
// Titles the service's catalogue does not hold: known only by name (type|title|year).
const SNAPSHOT={engine:'gorse',items:[],seedCount:1,catalogueCount:7,scope:'Synthetic',model:'Synthetic',watched:WATCHED,watchedNames:{netflix:['movie|namedfilm|2020']},importedEpisodeNames:{netflix:{'tv|importedshow|2020':{1:[1,2]}}}};
// Shell: every service request fails (Mac offline), so the cards must work from the saved snapshot alone.
const shellPage=`<!doctype html><html><head><meta charset="utf-8"><title>FlixTor TV</title></head><body><script>
localStorage.setItem('ftv.recommendationSnapshot.v1',JSON.stringify({schema:1,savedAt:Date.now(),data:${JSON.stringify(SNAPSHOT)}}));
(function(){function X(){}X.prototype.open=function(){};X.prototype.setRequestHeader=function(){};X.prototype.send=function(){var x=this;setTimeout(function(){if(x.onerror)x.onerror();},20);};window.XMLHttpRequest=X;}());
</script><script>${bundle}</script></body></html>`;
const shellURL=SHELL+'#'+encodeURIComponent(JSON.stringify({path:'/show/movies',href:'https://flixtor.to/show/movies',items:ITEMS}));
const seriesShellURL=SHELL+'#'+encodeURIComponent(JSON.stringify({path:'/show/tvshows',href:'https://flixtor.to/show/tvshows',items:ITEMS}));

const WATCH='https://flixtor.to/watch/movie/101-netflix-film';
const CSP="default-src 'self' blob:; connect-src 'self' *.xcdn.to; img-src 'self' img.xcdn.to image.tmdb.org data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'";
const watchPage=`<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}"><title>Watch</title></head><body>
<div class="watch-header" data-href="/watch/movie/101-netflix-film">Netflix Film (2020)</div>
<img alt="Poster Image" data-txt="Netflix Film" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
<div class="moreless-content">Synthetic synopsis.</div><div id="playerwrapper"><div id="player"></div></div>
<script>window.jwplayer=function(){return {getState:function(){return 'idle';},pause:function(){},play:function(){},stop:function(){}};};window.FTV_BRIDGE_ORIGIN='http://127.0.0.1:8773';</script>
<script>${bundle}</script></body></html>`;
// The shell stop used by the rating round trip: saves, then returns to the details page.
const rateShell=`<!doctype html><html><head><meta charset="utf-8"><title>FlixTor TV</title></head><body><script>
window.FTV_UPDATE_TOKEN='shell-token';(function(){function X(){}X.prototype.open=function(m,u){this.u=u;};X.prototype.setRequestHeader=function(){};
X.prototype.send=function(){var x=this;setTimeout(function(){x.status=200;x.responseText=/\\/updates\\//.test(x.u)?'{"healthy":true}':'{"saved":true,"state":{}}';x.onload();},30);};window.XMLHttpRequest=X;}());
</script><script>${bundle}</script></body></html>`;
const SERIES='https://flixtor.to/watch/tv/201/imported-show';
const seriesPage=`<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}"><title>Watch</title></head><body>
<div class="watch-header" data-href="/watch/tv/201/imported-show">Imported Show (2020)</div>
<img alt="Poster Image" data-txt="Imported Show" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
<div class="moreless-content">Synthetic synopsis.</div><div id="playerwrapper"><div id="player"></div></div>
<table><tbody>${[[1,1],[1,2],[1,3],[2,1]].map(e=>'<tr class="eplist" data-pid="201" data-pes="'+e[0]+'" data-pep="'+e[1]+'"><td><span class="epTitle">Part '+e[0]+'.'+e[1]+'</span></td><td class="nowrap"><span class="hidden-lg-down">2020</span></td></tr>').join('')}</tbody></table>
<script>window.jwplayer=function(){return {getState:function(){return 'idle';},pause:function(){},play:function(){},stop:function(){}};};window.FTV_BRIDGE_ORIGIN='http://127.0.0.1:8773';</script>
<script>${bundle}</script></body></html>`;
const seriesDetails=titles=>SERIES+'#ftv-details='+encodeURIComponent(JSON.stringify({profileId:PROFILE,titles:titles}));
const episodeRows='Array.prototype.map.call(document.querySelectorAll("#ftv .overlay .episode-row button"),function(b){return [b.querySelector(".episode-num").textContent,b.classList.contains("episode-watched"),b.getAttribute("aria-label")];})';
const actions='Array.prototype.map.call(document.querySelectorAll("#ftv .overlay .actions button"),function(b){return b.textContent;})';
const onSeries='location.origin==="https://flixtor.to"&&!!document.querySelector("#ftv .overlay .episode-row button")';
const details=ctx=>WATCH+'#ftv-details='+encodeURIComponent(JSON.stringify(Object.assign({profileId:PROFILE,titles:{}},ctx||{})));
const onDetails='location.origin==="https://flixtor.to"&&!!document.querySelector("#ftv .overlay .rating-row")';
const summary='Array.prototype.map.call(document.querySelectorAll("#ftv .overlay .watched-summary"),function(e){return e.textContent;})';
async function waitFor(p,expr,what){for(let i=0;i<160;i++){if(await p.evaluate(expr).catch(()=>false))return;await sleep(50);}throw Error('timed out waiting for '+what);}

(async()=>{
  const cdp=await launch();let failures=0;
  async function scenario(name,start,route,ready,fn){
    const p=await openPage(cdp,start,route);
    try{await p.navigate();await waitFor(p,ready,'page ready');await fn(p);console.log('  ok  '+name);}catch(e){failures++;console.log('  FAIL '+name+'\n       '+e.message.split('\n')[0]);}finally{await p.close();}}
  const detailRoute=u=>u.indexOf(WATCH)===0?watchPage:u.indexOf(SHELL)===0?rateShell:null;
  try{
    await scenario('shell cards: badge follows the resolved map, own choice beats FlixTor progress',shellURL,u=>u.indexOf(SHELL)===0?shellPage:null,'document.querySelectorAll("#ftv .card").length>=9',async p=>{
      const cards=await p.evaluate(`(function(){var out={};Array.prototype.forEach.call(document.querySelectorAll('#ftv .card'),function(c){var t=c.querySelector('.card-title').textContent,b=c.querySelector('.watched-badge');out[t]={badge:b?b.textContent:null,label:c.getAttribute('aria-label'),markup:!!c.querySelector('b')};});return out;}())`);
      assert.equal(cards['Netflix Film'].badge,'✓ WATCHED');assert.equal(cards['Netflix Film'].label,'Netflix Film, Watched on Netflix');
      assert.equal(cards['Prime Film'].label,'Prime Film, Watched on Prime Video');
      assert.equal(cards['Own Choice'].label,'Own Choice, Marked as watched');
      assert.equal(cards['Marked Unwatched'].badge,null,'"Not watched yet" wins over a finished FlixTor position');assert.equal(cards['Marked Unwatched'].label,'Marked Unwatched');
      assert.equal(cards['Finished Here'].label,'Finished Here, Watched on FlixTor','FlixTor\'s own finished movie still counts');
      assert.equal(cards['Never Seen'].badge,null);
      assert.equal(cards['Bad Entry'].badge,null,'unknown sources are dropped');assert.equal(cards['Bad Entry'].markup,false);
      const named=await p.evaluate(`Array.prototype.filter.call(document.querySelectorAll('#ftv .card'),function(c){return c.querySelector('.card-title').textContent==='Named Film';}).map(function(c){return c.getAttribute('aria-label');})`);
      assert.deepEqual(named,['Named Film, Watched on Netflix','Named Film'],'a title outside the catalogue is matched by name and year');
    });
    await scenario('shell to series page: episodes known only by name travel with the title and are ticked',seriesShellURL,u=>u.indexOf(SHELL)===0?shellPage:u.indexOf(SERIES)===0?seriesPage:null,'document.querySelectorAll("#ftv .card").length>=1',async p=>{
      assert(await p.evaluate(`(function(){var c=Array.prototype.filter.call(document.querySelectorAll('#ftv .card'),function(c){return c.querySelector('.card-title').textContent==='Imported Show';})[0];if(!c)return false;c.click();return true;}())`));
      await waitFor(p,onSeries,'series page');
      assert.deepEqual((await p.evaluate(episodeRows)).map(r=>r[1]),[true,true,false]);assert((await p.evaluate(actions)).includes('▶ Next: S1 · E3'));
    });
    await scenario('details: an imported entry in the navigation context is shown with its source',details({watched:{'flixtor:movie:101':{watched:true,source:'netflix'}}}),detailRoute,onDetails,async p=>{
      assert.deepEqual(await p.evaluate(summary),['✓ Watched on Netflix']);
    });
    await scenario('details: no entry, another title\'s entry, or "not watched" shows nothing',details({watched:{'flixtor:movie:999':{watched:true,source:'netflix'},'flixtor:movie:101':{watched:false,source:'manual'}}}),detailRoute,onDetails,async p=>{
      assert.deepEqual(await p.evaluate(summary),[]);
    });
    await scenario('details: a saved rating marks the title as watched on return',details(),detailRoute,onDetails,async p=>{
      assert.deepEqual(await p.evaluate(summary),[]);
      assert(await p.evaluate(`(function(){var b=Array.prototype.filter.call(document.querySelectorAll('#ftv .overlay .rating-row button'),function(e){return e.textContent==='Loved it';})[0];if(!b)return false;b.click();return true;}())`));
      await waitFor(p,onDetails+'&&/Saved: Loved it/.test((document.querySelector("#ftv .rating-row [role=status]")||{}).textContent||"")','return with saved status');
      assert.deepEqual(await p.evaluate(summary),['✓ Marked as watched']);
    });
    await scenario('series: episodes finished on a streaming service are ticked, and Next continues after them',seriesDetails({'flixtor:tv:201':{completedSeasons:[],completedThrough:null,episodes:{},imported:{netflix:{1:[1,2]}}}}),u=>u.indexOf(SERIES)===0?seriesPage:null,onSeries,async p=>{
      assert.deepEqual(await p.evaluate(episodeRows),[['01',true,'Episode 1: Part 1.1 · Watched'],['02',true,'Episode 2: Part 1.2 · Watched'],['03',false,'Episode 3: Part 1.3']]);
      assert((await p.evaluate(actions)).includes('▶ Next: S1 · E3'));
    });
    await scenario('series: the profile\'s own "not watched" beats an imported episode',seriesDetails({'flixtor:tv:201':{completedSeasons:[],completedThrough:null,episodes:{'1:1':{watched:false}},imported:{netflix:{1:[1,2]}}}}),u=>u.indexOf(SERIES)===0?seriesPage:null,onSeries,async p=>{
      assert.deepEqual((await p.evaluate(episodeRows)).map(r=>r[1]),[false,true,false]);
      assert((await p.evaluate(actions)).includes('▶ Next: S1 · E1'));
    });
  }finally{cdp.close();}
  if(failures){console.log('FAIL: '+failures+' watched scenario(s).');process.exit(1);}
  console.log('PASS: watched badge on shell cards from the saved snapshot (Netflix, Prime Video, own choice, FlixTor progress, precedence, invalid entries) watched line on details via navigation context and rating round trip, and imported episode ticks with own-choice precedence on a series page. Samsung behavior needs a TV check.');
})().catch(e=>{console.error(e);process.exit(1);});
