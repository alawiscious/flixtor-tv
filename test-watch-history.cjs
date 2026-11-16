const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const data={'pos:4018954:2:13':'2400:2400:100','pos:4018954:2:14':'900:2400:200','pos:7':'50:100:300','pos:4018954:2:15':'broken'};
const ctx={localStorage:{get length(){return Object.keys(data).length},key:i=>Object.keys(data)[i],getItem:k=>data[k]},window:{},setTimeout,clearTimeout};vm.createContext(ctx);vm.runInContext(fs.readFileSync('src/watch-history.js','utf8'),ctx);const h=ctx.FTV_HISTORY;
assert.equal(h.latest('4018954',true).number,14);assert.equal(h.latest('4018954',true).position,900);assert.equal(h.latest('7',false).season,0);assert.equal(h.parse('pos:1:2:3','98:100:123').complete,true);
for(const value of ['0:0:5','NaN:10:3','-1:50:3','1:2','1:2:0'])assert.equal(h.parse('pos:1',value),null);
assert.equal(h.parse('secret:1','1:2:3'),null);assert(h.label(h.latest('4018954',true)).includes('S2 · E14'));assert.equal(h.decorate({url:'https://flixtor.to/watch/tv/4018954/seal-team'}).resume.number,14);
const episodes=[{season:3,number:1},{season:2,number:15},{season:2,number:14}];assert.equal(h.next(episodes,{season:2,number:14}).number,15);assert.equal(h.next(episodes,{season:2,number:15}).season,3);assert.equal(h.next(episodes,{season:3,number:1}),null);assert.equal(h.next(episodes,{season:1,number:1}),null);
// The native player is the sole end-of-episode scheduler: overlay only delegates user clicks.
const nextSource=fs.readFileSync('src/next-episode.js','utf8');assert(!/\.ended\s*\)\s*advance\(/.test(nextSource));assert(nextSource.includes('ep.native.click()'));
// Title-level watched state: the service's resolved map first, then FlixTor's own finished movie position.
{const film={url:'https://flixtor.to/watch/movie/7/example'},show={url:'https://flixtor.to/watch/tv/4018954/seal-team'},done={complete:true},plain=v=>JSON.parse(JSON.stringify(v));
 const map={'flixtor:movie:7':{watched:true,source:'netflix'},'flixtor:tv:4018954':{watched:false,source:'manual'},'flixtor:movie:8':{watched:true,source:'somewhere'},'flixtor:movie:9':{watched:'yes',source:'manual'}};
 assert.deepEqual(plain(h.titleState(film,map)),{watched:true,source:'netflix'});assert.equal(h.titleLabel(h.titleState(film,map)),'Watched on Netflix');
 assert.deepEqual(plain(h.titleState(Object.assign({resume:done},show),map)),{watched:false,source:'manual'},'own choice beats native progress');assert.equal(h.titleLabel(h.titleState(show,map)),'');
 assert.deepEqual(plain(h.titleState({url:'https://flixtor.to/watch/tv/7/example',resume:done},map)),{watched:false,source:'none'},'ids are type-scoped and one finished episode never marks a series');
 for(const id of [8,9])assert.deepEqual(plain(h.titleState({url:'https://flixtor.to/watch/movie/'+id+'/x'},map)),{watched:false,source:'none'},'invalid entries are ignored');
 assert.deepEqual(plain(h.titleState({url:'https://flixtor.to/watch/movie/8/x',resume:done},map)),{watched:true,source:'native'});assert.equal(h.titleLabel({watched:true,source:'native'}),'Watched on FlixTor');
 assert.equal(h.titleLabel({watched:true,source:'amazon'}),'Watched on Prime Video');assert.equal(h.titleLabel({watched:true,source:'manual'}),'Marked as watched');
 for(const bad of [null,undefined,{},{url:'https://example.com/x'}])assert.deepEqual(plain(h.titleState(bad,map)),{watched:false,source:'none'});
 assert.deepEqual(plain(h.titleState(film,null)),{watched:false,source:'none'});assert.equal(h.titleLabel(null),'');
 // Finished titles the service only knows by name (same cases as backend/test_watched.py NAME_CASES).
 const url=kind=>kind==='short'?'https://flixtor.to/short/1':'https://flixtor.to/watch/'+kind+'/1/x';
 for(const [[kind,title,year],expected] of [[['movie','Am\u00e9lie','2001'],'movie|amelie|2001'],[['tv','Se7en: The  Beginning!',2019],'tv|se7enthebeginning|2019'],[['movie','Stra\u00dfe','1999'],'movie|strae|1999'],
   [['movie','Film','2020 \u00b7 1h 30m'],'movie|film|2020'],[['movie','Film',''],null],[['movie','!!!','2020'],null],[['short','Film','2020'],null],[['movie','Film','0000'],null]])assert.equal(h.nameKey({url:url(kind),title,year}),expected||'',JSON.stringify([kind,title,year]));
 assert.equal(h.nameKey(null),'');
 const named={url:'https://flixtor.to/watch/movie/50/named',title:'Named Film',year:'2020'},names={netflix:['movie|other|2020'],amazon:['movie|namedfilm|2020']};
 assert.deepEqual(plain(h.titleState(named,map,names)),{watched:true,source:'amazon'});assert.equal(h.titleLabel(h.titleState(named,map,names)),'Watched on Prime Video');
 assert.deepEqual(plain(h.titleState(Object.assign({},named,{year:'2021'}),map,names)),{watched:false,source:'none'},'another year is another title');
 assert.deepEqual(plain(h.titleState(Object.assign({},named,{url:'https://flixtor.to/watch/tv/50/named'}),map,names)),{watched:false,source:'none'},'a series of the same name is another title');
 assert.deepEqual(plain(h.titleState(named,{'flixtor:movie:50':{watched:false,source:'manual'}},names)),{watched:false,source:'manual'},'own "not watched" beats a name match');
 assert.deepEqual(plain(h.titleState(Object.assign({resume:done},named),map,names)),{watched:true,source:'amazon'},'a name match ranks above native completion');
 for(const bad of [null,[],'x',{amazon:'movie|namedfilm|2020'},{amazon:{'movie|namedfilm|2020':true}},{elsewhere:['movie|namedfilm|2020']}])assert.deepEqual(plain(h.titleState(named,map,bad)),{watched:false,source:'none'});
 // Episode facts for a series: by catalogue id first; an import layer known only by name fills in below the profile's own facts.
 const series={url:'https://flixtor.to/watch/tv/60/named-show',title:'Named Show',year:'2018'},byName={netflix:{'tv|namedshow|2018':{1:[1,2]}},amazon:{'tv|othershow|2018':{1:[9]}}};
 assert.equal(h.episodeFacts(series,{},{}),null);assert.equal(h.episodeFacts(named,{},byName),null,'films have no episode facts');
 assert.deepEqual(plain(h.episodeFacts(series,{},byName)),{completedSeasons:[],completedThrough:null,episodes:{},imported:{netflix:{1:[1,2]}}});
 const own={completedSeasons:[3],completedThrough:null,episodes:{'1:1':{watched:false}},source:'explicit_user'},ownSnapshot=JSON.stringify(own);
 const merged=h.episodeFacts(series,{'flixtor:tv:60':own},byName);assert.deepEqual(plain(merged),Object.assign({},own,{imported:{netflix:{1:[1,2]}}}));assert.equal(JSON.stringify(own),ownSnapshot,'the profile\'s own facts are not modified');
 assert.deepEqual(plain(h.episodeState(null,1,1,merged)),{watched:false,source:'manual'});assert.deepEqual(plain(h.episodeState(null,1,2,merged)),{watched:true,source:'netflix'});assert.deepEqual(plain(h.episodeState(null,3,7,merged)),{watched:true,source:'manual'});
 const held={imported:{amazon:{2:[5]}}};assert.equal(h.episodeFacts(series,{'flixtor:tv:60':held},byName),held,'the id-keyed import layer is the answer once the catalogue holds the series');
 assert.equal(h.episodeFacts(series,{'flixtor:tv:60':own},{netflix:{'tv|namedshow|2019':{1:[1]}},constructor:{}}),own);
 console.log('PASS: title watched precedence (service map, then name match, then native movie completion), shared name-key cases, episode facts by id or name, source wording and invalid entries.');}
console.log('PASS: real native progress parsing, most recent episode, completion, invalid data, movie/series separation, season boundary and finale.');
// Deterministic native-selection harness: no real playback or household state.
function nextHarness(){
  let active={season:2,number:14},clicks=[],tick,mutate,reads=0,now=0,disconnected=false;
  const video={duration:2400,currentTime:2390,ended:false,focus(){document.activeElement=this}};
  const document={documentElement:{},activeElement:null,createElement:el,querySelector(s){return s==='.eplist.table-active'&&active?{getAttribute:k=>k==='data-pes'?String(active.season):String(active.number)}:s==='#autoplay-toggle'?{checked:true}:null}};
  function el(){return {nodeType:1,className:'',style:{},children:[],appendChild(e){e.parentNode=this;this.children.push(e)},addEventListener(name,fn){this[name]=fn},remove(){this.removed=true},focus(){document.activeElement=this}}}
  const parent=el();parent.querySelector=s=>s==='video'?video:null;
  let onRead=null,onClick=null,episodes=[{season:2,number:14},{season:2,number:15},{season:3,number:1}];
  function wire(){episodes.forEach(ep=>{ep.native={click(){clicks.push(ep.season+':'+ep.number);if(onClick)onClick(ep)}}})}wire();
  function Observer(fn){mutate=fn;this.observe=()=>{};this.disconnect=()=>{disconnected=true}}
  const context={document,FTV_HISTORY:h,Date:{now:()=>now},MutationObserver:Observer,setInterval:fn=>{tick=fn;return 1},clearInterval:()=>{tick=null}};
  vm.createContext(context);vm.runInContext(nextSource,context);
  const manager=context.FTV_NEXT.attach(parent,()=>{reads++;if(onRead)onRead();return episodes});
  return {manager,panel:parent.children[0],video,document,clicks,get reads(){return reads},get stopped(){return tick===null&&disconnected},tick(){tick()},time(ms){now+=ms},active(value){active=value},onClick(fn){onClick=fn},onRead(fn){onRead=fn},replace(values){episodes=values;wire();mutate([{target:{nodeType:1,className:'eplist'},addedNodes:[],removedNodes:[]}])},unrelated(){mutate([{target:{nodeType:1,className:'jwplayer'},addedNodes:[],removedNodes:[]}])}};
}
let n=nextHarness(),panel=n.panel,manager=n.manager;
assert.equal(panel.style.display,'block');assert(panel.children[0].textContent.includes('starts in 10s'));
n.video.ended=true;n.tick();assert.equal(n.clicks.length,0,'native autoplay alone handles completion');
manager.handleKey({key:'ArrowDown'});assert.equal(n.document.activeElement,panel.children[1]);
assert(manager.advance());assert.equal(n.document.activeElement,n.video,'selection hides prompt and restores video focus');assert(!manager.advance());assert.equal(n.clicks.length,1);
n.time(3999);n.tick();assert.equal(panel.style.display,'none','delayed native selection remains pending');assert(!manager.advance());
n.active({season:2,number:15});assert(!manager.advance('2:14'),'stale action cannot skip externally opened episode');n.video.currentTime=0;n.video.ended=false;n.tick();assert.equal(panel.style.display,'none');assert.equal(manager.next().season,3);
assert(manager.advance());assert.equal(n.clicks.length,2);n.active({season:3,number:1});n.tick();assert.equal(manager.next(),null);assert(!manager.advance());manager.destroy();assert(n.stopped);assert(panel.removed);
// An ignored click is retryable after the pending window; the retry addresses the same exact row.
n=nextHarness();assert(n.manager.advance());n.time(4000);n.tick();assert.equal(n.panel.style.display,'block');assert(n.manager.advance());assert.deepEqual(n.clicks,['2:15','2:15']);assert(!n.manager.advance());n.manager.destroy();
// A native click exception must not permanently disable next episode.
n=nextHarness();n.onClick(()=>{throw Error('detached native row')});assert.equal(n.manager.advance(),false);assert.equal(n.panel.style.display,'block');n.onClick(null);assert(n.manager.advance());n.manager.destroy();
// Native autoplay changes the row while target data is being read: no competing click.
n=nextHarness();n.replace([{season:2,number:14},{season:2,number:15},{season:3,number:1}]);n.onRead(()=>n.active({season:2,number:15}));assert.equal(n.manager.advance('2:14'),false);assert.equal(n.clicks.length,0);n.onRead(null);n.tick();assert.equal(n.manager.next().season,3);n.manager.destroy();
// The expensive history reader only runs when actual episode inputs change.
n=nextHarness();for(let i=0;i<120;i++){n.tick();n.manager.next()}assert.equal(n.reads,1);
n.unrelated();n.tick();assert.equal(n.reads,1,'player UI mutations do not invalidate episode cache');
n.replace([{season:2,number:14},{season:2,number:16}]);n.tick();assert.equal(n.reads,2);assert.equal(n.manager.next().number,16);
n.manager.handleKey({key:'ArrowDown'});n.video.currentTime=0;n.tick();assert.equal(n.document.activeElement,n.video,'rewinding out of countdown restores focus');
n.video.currentTime=2390;n.tick();n.manager.handleKey({key:'ArrowDown'});n.replace([]);n.tick();assert.equal(n.manager.next(),null);assert.equal(n.panel.style.display,'none');assert.equal(n.document.activeElement,n.video,'missing/finale episode DOM hides prompt without stranded focus');assert(!n.manager.advance());
n.replace([{season:2,number:14},{season:2,number:15}]);n.tick();assert.equal(n.manager.next().number,15,'late episode DOM population invalidates an empty target');
n.active(null);n.tick();assert.equal(n.manager.next(),null);assert(!n.manager.advance());n.manager.destroy();
console.log('PASS: native-only scheduler, bounded selection recovery, delayed selection, external autoplay race, focus restoration, episode-input caching, missing DOM/finale and observer teardown.');

// Decoration must read one history snapshot per catalogue, not once per card.
let storageKeys=0,storageReads=0;const entries=Object.fromEntries(Array.from({length:5000},(_,i)=>['pos:'+String(i+1)+':2:14','900:2400:'+String(i+1)]));
let entryKeys=Object.keys(entries);const batchContext={localStorage:{get length(){return entryKeys.length},key(i){storageKeys++;return entryKeys[i]},getItem(k){storageReads++;return entries[k]}},window:{},setTimeout,clearTimeout};vm.createContext(batchContext);vm.runInContext(fs.readFileSync('src/watch-history.js','utf8'),batchContext);
const batchItems=Array.from({length:400},(_,i)=>({url:'https://flixtor.to/watch/tv/'+(i+1)+'/example'}));batchContext.FTV_HISTORY.decorateAll(batchItems);assert.equal(storageKeys,5000);assert.equal(storageReads,5000);assert.equal(batchItems[0].resume.number,14);
entries['pos:1:2:15']='1000:2400:999999';entryKeys=Object.keys(entries);batchContext.FTV_HISTORY.decorateAll(batchItems);assert.equal(batchItems[0].resume.number,15,'a new batch sees newly synced progress');console.log('PASS: one history scan per catalogue and fresh progress on the next batch.');

// Profile completion facts never become native playback positions.
function state(record,season,number,facts){return JSON.parse(JSON.stringify(h.episodeState(record,season,number,facts)));}
const nativeComplete=Object.freeze({season:2,number:18,complete:true,position:2400,duration:2400,timestamp:123});
const partial=Object.freeze({season:2,number:18,complete:false,position:600,duration:2400,timestamp:456});
const completionFacts=Object.freeze({completedSeasons:Object.freeze([1]),completedThrough:Object.freeze({season:2,episode:17})});
assert.deepEqual(state(partial,2,17,completionFacts),{watched:true,source:'manual'});
assert.deepEqual(state(null,1,999,completionFacts),{watched:true,source:'manual'});
assert.deepEqual(state(null,1,999,{completedThrough:{season:2,episode:17}}),{watched:true,source:'manual'},'through marker includes earlier seasons');
assert.deepEqual(state(nativeComplete,2,18,{completedSeasons:[2]}),{watched:true,source:'manual'},'manual source wins over native completion');
assert.deepEqual(state(null,1,1,{completedSeasons:['1']}),{watched:false,source:'none'});
assert.deepEqual(state(null,2,18,completionFacts),{watched:false,source:'none'});
assert.deepEqual(state(null,3,1,completionFacts),{watched:false,source:'none'});
assert.deepEqual(state(nativeComplete,2,18,completionFacts),{watched:true,source:'native'});
assert.deepEqual(state(nativeComplete,2,19,completionFacts),{watched:false,source:'none'},'another episode cannot borrow native completion');
assert.deepEqual(state(partial,2,18,completionFacts),{watched:false,source:'none'});
const explicitFacts={completedSeasons:[1,2],completedThrough:{season:3,episode:5},episodes:{'2:18':{watched:false},'4:1':{watched:true}}};
assert.deepEqual(state(nativeComplete,2,18,explicitFacts),{watched:false,source:'manual'},'explicit unwatched overrides ranges and native completion');
assert.deepEqual(state(null,4,1,explicitFacts),{watched:true,source:'manual'});
assert.deepEqual(state(null,2,18,{episodes:{'2:18':{watched:'true'}}}),{watched:false,source:'none'});
for(const invalid of [0,-1,1.5,NaN,Infinity,'2']){
  assert.deepEqual(state(nativeComplete,invalid,18,explicitFacts),{watched:false,source:'none'});
  assert.deepEqual(state(null,2,invalid,completionFacts),{watched:false,source:'none'});
  assert.deepEqual(state(null,1,1,{completedThrough:{season:invalid,episode:17}}),{watched:false,source:'none'});
  assert.deepEqual(state(null,1,1,{completedThrough:{season:2,episode:invalid}}),{watched:false,source:'none'});
}
assert.deepEqual(state(null,1,1,{completedSeasons:'1'}),{watched:false,source:'none'});
assert.deepEqual(state(null,2,18,null),{watched:false,source:'none'});
const orderedCandidates=[Object.freeze({season:3,number:1}),Object.freeze({season:2,number:19}),Object.freeze({season:2,number:18,resume:nativeComplete}),Object.freeze({season:1,number:1}),Object.freeze({season:2,number:17})];
const candidatesSnapshot=JSON.stringify(orderedCandidates),nativeSnapshot=JSON.stringify(nativeComplete),factsSnapshot=JSON.stringify(completionFacts);
assert.equal(h.nextUnwatched(orderedCandidates,completionFacts),orderedCandidates[1]);
assert.equal(h.nextUnwatched(orderedCandidates,explicitFacts),orderedCandidates[2],'explicit unwatched is selectable for replay');
assert.equal(h.nextUnwatched([{season:1,number:1}],completionFacts),null);
assert.equal(h.nextUnwatched([],completionFacts),null);
assert.equal(h.nextUnwatched([null,{season:0,number:1},{season:1,number:0}],{}),null);
assert.equal(JSON.stringify(orderedCandidates),candidatesSnapshot);assert.equal(JSON.stringify(nativeComplete),nativeSnapshot);assert.equal(JSON.stringify(completionFacts),factsSnapshot);
assert.deepEqual(Object.keys(state(null,1,1,completionFacts)).sort(),['source','watched']);
assert.deepEqual(state(null,1,1,{}),{watched:false,source:'none'},'completion facts for one profile do not bleed into another');
// Imported episode completion sits between the profile's own facts and native completion.
{const imported={netflix:{2:[17,18]},amazon:{2:[18],5:[1]}},facts={episodes:{'2:17':{watched:false}},imported};
 assert.deepEqual(state(null,2,18,facts),{watched:true,source:'netflix'},'services are read in one fixed order');
 assert.deepEqual(state(null,5,1,facts),{watched:true,source:'amazon'});
 assert.deepEqual(state(nativeComplete,2,18,facts),{watched:true,source:'netflix'},'import ranks above native completion');
 assert.deepEqual(state(null,2,17,facts),{watched:false,source:'manual'},'own "not watched" beats an import');
 assert.deepEqual(state(null,2,18,{completedSeasons:[2],imported}),{watched:true,source:'manual'},'own completed season is reported as the profile\'s own');
 assert.deepEqual(state(null,2,19,facts),{watched:false,source:'none'});assert.deepEqual(state(null,3,18,facts),{watched:false,source:'none'},'another season cannot borrow an episode number');
 for(const bad of [null,'netflix',[],{netflix:null},{netflix:{2:'18'}},{netflix:{2:{18:true}}},{netflix:{2:['18']}},{elsewhere:{2:[18]}}])assert.deepEqual(state(null,2,18,{imported:bad}),{watched:false,source:'none'});
 const list=[{season:2,number:17},{season:2,number:18},{season:2,number:19}];
 assert.equal(h.nextUnwatched(list,{imported:{netflix:{2:[17,18]}}}),list[2],'next episode continues after what was finished on a service');assert.equal(h.nextUnwatched(list,facts),list[0]);
 console.log('PASS: imported episode completion (precedence below own facts and above native, fixed service order, invalid shapes, next unwatched).');}
console.log('PASS: profile episode facts, explicit unwatched precedence, native completion identity, invalid facts, first available unwatched, no mutation and no fabricated playback positions.');

{const special=h.parse('pos:42:0:1','1200:1200:1000');assert.equal(special.type,'tv');assert.equal(h.label(special),'S0 · E1 · Watched');assert.equal(h.parse('pos:42','1200:1200:1000').type,'movie');}
console.log('PASS: season-zero specials retain series identity and episode labels.');
