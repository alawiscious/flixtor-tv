const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const data={'pos:4018954:2:13':'2400:2400:100','pos:4018954:2:14':'900:2400:200','pos:7':'50:100:300','pos:4018954:2:15':'broken'};
const ctx={localStorage:{get length(){return Object.keys(data).length},key:i=>Object.keys(data)[i],getItem:k=>data[k]},window:{},setTimeout,clearTimeout};vm.createContext(ctx);vm.runInContext(fs.readFileSync('src/watch-history.js','utf8'),ctx);const h=ctx.FTV_HISTORY;
assert.equal(h.latest('4018954',true).number,14);assert.equal(h.latest('4018954',true).position,900);assert.equal(h.latest('7',false).season,0);assert.equal(h.parse('pos:1:2:3','98:100:123').complete,true);
for(const value of ['0:0:5','NaN:10:3','-1:50:3','1:2','1:2:0'])assert.equal(h.parse('pos:1',value),null);
assert.equal(h.parse('secret:1','1:2:3'),null);assert(h.label(h.latest('4018954',true)).includes('S2 · E14'));assert.equal(h.decorate({url:'https://flixtor.to/watch/tv/4018954/seal-team'}).resume.number,14);
const episodes=[{season:3,number:1},{season:2,number:15},{season:2,number:14}];assert.equal(h.next(episodes,{season:2,number:14}).number,15);assert.equal(h.next(episodes,{season:2,number:15}).season,3);assert.equal(h.next(episodes,{season:3,number:1}),null);assert.equal(h.next(episodes,{season:1,number:1}),null);
// The native player is the sole end-of-episode scheduler: overlay only delegates user clicks.
const nextSource=fs.readFileSync('src/next-episode.js','utf8');assert(!/\.ended\s*\)\s*advance\(/.test(nextSource));assert(nextSource.includes("locked===key"));assert(nextSource.includes('ep.native.click()'));
console.log('PASS: real native progress parsing, most recent episode, completion, invalid data, movie/series separation, season boundary and finale.');
let active={season:2,number:14},clicks=0,tick,video={duration:2400,currentTime:2390,ended:false};
function el(){return {style:{},children:[],appendChild(e){e.parentNode=this;this.children.push(e)},addEventListener(name,fn){this[name]=fn},remove(){this.removed=true},focus(){document.activeElement=this}}}
const document={createElement:el,querySelector:s=>s==='.eplist.table-active'?{getAttribute:k=>k==='data-pes'?String(active.season):String(active.number)}:s==='#autoplay-toggle'?{checked:true}:null};
const parent=el();parent.querySelector=s=>s==='video'?video:null;
const nextCtx={document,FTV_HISTORY:h,setInterval:fn=>{tick=fn;return 1},clearInterval:()=>{tick=null}};vm.createContext(nextCtx);vm.runInContext(nextSource,nextCtx);
const nativeEpisodes=[{season:2,number:14},{season:2,number:15,native:{click(){clicks++}}},{season:3,number:1,native:{click(){clicks++}}}];
const manager=nextCtx.FTV_NEXT.attach(parent,()=>nativeEpisodes),panel=parent.children[0];assert.equal(panel.style.display,'block');assert(panel.children[0].textContent.includes('starts in 10s'));
video.ended=true;tick();assert.equal(clicks,0,'native autoplay alone handles completion');assert(manager.advance());assert(!manager.advance());assert.equal(clicks,1);
active={season:2,number:15};assert(!manager.advance('2:14'),'stale countdown cannot skip the episode native autoplay just opened');video={duration:2500,currentTime:0,ended:false};tick();assert.equal(panel.style.display,'none');assert.equal(manager.next().season,3);assert(manager.advance());assert.equal(clicks,2);
active={season:3,number:1};tick();assert.equal(manager.next(),null);assert(!manager.advance());manager.destroy();assert.equal(tick,null);assert(panel.removed);
console.log('PASS: visible countdown, no competing end scheduler, double-click lock, native episode replacement, finale and teardown.');
