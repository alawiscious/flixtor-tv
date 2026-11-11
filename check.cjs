// Contract checks complement browser QA; no Samsung runtime is simulated here.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync(__dirname+'/src/app.js','utf8');
new vm.Script(fs.readFileSync(__dirname+'/tv.js','utf8'));
assert(!app.includes('localStorage'),'Native Favorites/progress must not become an overlay-local list');
assert(app.includes('native.click()'),'Favorites must delegate to the native site action');
assert(app.includes('ep.native.click()'),'Episode selection must delegate to the native player action');
const context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/preview/sample.js','utf8'),context);
const items=context.window.FTV_PREVIEW;
assert.equal(items.length,12);assert.equal(new Set(items.map(i=>i.url)).size,12);
const eps=items[0].episodes;assert.equal(eps.length,18);assert.equal(new Set(eps.map(e=>e.season+':'+e.number)).size,18);
for(const i of items)assert(/^\/watch\/(tv|movie)\/\d+\//.test(i.url));
console.log('PASS: syntax, native-storage delegation guard, unique title IDs and season/episode fixtures.');
console.log('Browser QA is required for focus, navigation, motion and layout. Physical TV testing is required for TizenBrew injection and playback.');

const filterContext={URL};vm.createContext(filterContext);vm.runInContext(fs.readFileSync(__dirname+'/src/filters.js','utf8'),filterContext);
const filter=filterContext.FTV_FILTERS,state=filter.read('https://flixtor.to/show/movies?yrf=2020&yrt=2026&rating=7');
assert(filter.matches({year:'2020',rating:'7'},state));
assert(filter.matches({year:'2026',rating:'9.1'},state));
for(const item of [{year:'2019',rating:'8'},{year:'2027',rating:'8'},{year:'2025',rating:'6.9'},{year:'2025',rating:''},{year:'',rating:'9'}])assert(!filter.matches(item,state));
const filteredURL=new URL(filter.target('https://flixtor.to/show/movies?yrf=2020&yrt=2026&rating=7&genre=Drama&sort=best&page=4#ftv-original','rating',8));
assert.equal(filteredURL.searchParams.get('yrf'),'2020');assert.equal(filteredURL.searchParams.get('yrt'),'2026');assert.equal(filteredURL.searchParams.get('rating'),'8');assert.equal(filteredURL.searchParams.get('genre'),'Drama');assert.equal(filteredURL.searchParams.get('sort'),'best');assert(!filteredURL.searchParams.has('page'));assert.equal(filteredURL.hash,'');
assert(!new URL(filter.target(filteredURL.href,'rating',0)).searchParams.has('rating'));
assert.equal(new URL(filter.target(filteredURL.href,'reset',0)).search,'');
assert.throws(()=>filter.target(filteredURL.href,'yrf',2027));assert.throws(()=>filter.target('https://example.com/show/movies','rating',8));
console.log('PASS: inclusive year/rating bounds, unknown metadata, pagination reset, preserved native query and invalid ranges.');
// Live genre queries use FlixTor's complete native genre vocabulary, independent of the visible page.
const genreOptions=Array.from(filter.genres());
assert.deepEqual(genreOptions,['All genres','Action','Adventure','Animation','Comedy','Crime','Documentary','Drama','Family','History','Horror','Music','Mystery','Romance','Sci-Fi & Fantasy','TV-Movie','Thriller','War','Western']);
genreOptions.push('Unsupported');assert(!Array.from(filter.genres()).includes('Unsupported'),'options are defensive copies');
for(const genre of Array.from(filter.genres()).slice(1)){
  const url=new URL(filter.target(filteredURL.href,'genre',genre));
  assert.equal(url.searchParams.get('genre'),genre);assert.equal(filter.read(url.href).genre,genre);
  assert.equal(url.searchParams.get('yrf'),'2020');assert.equal(url.searchParams.get('yrt'),'2026');assert.equal(url.searchParams.get('rating'),'8');assert.equal(url.searchParams.get('sort'),'best');assert(!url.searchParams.has('page'));
}
const sciState=filter.read('https://flixtor.to/show/movies?genre=Sci-Fi%20%26%20Fantasy&yrf=2020&rating=7');
assert.equal(sciState.genre,'Sci-Fi & Fantasy');
for(const alias of ['Science-Fiction','Sci-Fi','Science Fiction','Fantasy','Sci-Fi & Fantasy']){
 assert.equal(filter.read('https://flixtor.to/show/movies?genre='+encodeURIComponent(alias)).genre,'Sci-Fi & Fantasy');
 assert.equal(new URL(filter.target(filteredURL.href,'genre',alias)).searchParams.get('genre'),'Sci-Fi & Fantasy');
 assert(filter.matches({year:2025,rating:8,meta:'Drama, '+alias},sciState));
}
assert(filter.matches({year:2025,rating:8,genres:['Science-Fiction']},sciState));
assert(filter.matches({year:2025,rating:8,genre:'Sci-Fi'},sciState));
for(const item of [{year:2025,rating:8,meta:'Drama'},{year:2019,rating:8,meta:'Sci-Fi'},{year:2025,rating:6,meta:'Sci-Fi'},{year:2025,rating:8,meta:'Not Sci-Fi'},{year:2025,rating:8}])assert(!filter.matches(item,sciState));
for(const clear of ['','all','All genres']){
 const cleared=new URL(filter.target('https://flixtor.to/show/movies?genre=Drama&page=9&rating=7','genre',clear));
 assert(!cleared.searchParams.has('genre'));assert(!cleared.searchParams.has('page'));assert.equal(cleared.searchParams.get('rating'),'7');assert.equal(filter.read(cleared.href).genre,'');
}
for(const invalid of ['Unsupported','Sci-Fi<script>',null,0,{}]){
 assert.throws(()=>filter.target(filteredURL.href,'genre',invalid));
 assert.equal(filter.read('https://flixtor.to/show/movies?genre='+encodeURIComponent(String(invalid))).genre,'');
}
assert.equal(filter.read('https://flixtor.to/show/movies').genre,'');
assert.equal(filter.read('https://flixtor.to/show/movies?genre=tv%20movie').genre,'TV-Movie');
assert.equal(new URL(filter.target(filteredURL.href,'reset',0)).search,'');
console.log('PASS: full native genre choices, canonical sci-fi aliases, exact metadata matching, invalid genre rejection, clear/reset and preserved year/rating/sort.');
for(const sort of ['latest','best','name']){
 const sorted=new URL(filter.target('https://flixtor.to/show/movies?genre=Drama&yrf=2020&yrt=2026&rating=7&page=8#ftv-original','sort',sort));
 assert.equal(sorted.searchParams.get('sort'),sort);assert.equal(filter.read(sorted.href).sort,sort);assert(!sorted.searchParams.has('page'));assert.equal(sorted.hash,'');
 assert.equal(sorted.searchParams.get('genre'),'Drama');assert.equal(sorted.searchParams.get('yrf'),'2020');assert.equal(sorted.searchParams.get('yrt'),'2026');assert.equal(sorted.searchParams.get('rating'),'7');
}
const defaultSort=new URL(filter.target(filteredURL.href,'sort',''));assert(!defaultSort.searchParams.has('sort'));assert.equal(defaultSort.searchParams.get('genre'),'Drama');assert.equal(filter.read(defaultSort.href).sort,'');
for(const invalid of ['newest','BEST',null,0,{}]){assert.throws(()=>filter.target(filteredURL.href,'sort',invalid));assert.equal(filter.read('https://flixtor.to/show/movies?sort='+encodeURIComponent(String(invalid))).sort,'');}
console.log('PASS: native latest/best/name sorting, default clearing, invalid sort rejection, pagination reset and preserved genre/year/rating.');



const playerContext={};vm.createContext(playerContext);vm.runInContext(fs.readFileSync(__dirname+'/src/player.js','utf8'),playerContext);
const quality=playerContext.FTV_PLAYER;
assert.equal(quality.bestQuality([{label:'Auto'},{label:'720p'},{label:'1080p'},{label:'480p'}]),2);
assert.equal(quality.bestQuality([{label:'Auto',height:2160},{label:'1080p'},{label:'4K'}]),2);
assert.equal(quality.bestQuality([]),-1);
let selected=0;const levels=[{label:'Auto'},{label:'720p'},{label:'1080p'}];
assert(quality.preferHighest({getQualityLevels:()=>levels,getCurrentQuality:()=>selected,setCurrentQuality:i=>{selected=i;}}));assert.equal(selected,2);
assert(!quality.preferHighest({getQualityLevels:()=>{throw new Error('not ready');}}));
console.log('PASS: highest offered quality, Auto exclusion, empty/unready player and selected-quality confirmation.');

// Player sound restores mute/zero-volume states without raising a nonzero level.
let mute=true,vol=0;const soundPlayer={setMute:v=>{mute=v;},getVolume:()=>vol,setVolume:v=>{vol=v;}};const soundVideo={muted:true,volume:0};assert(quality.setSound(soundPlayer,soundVideo,true));assert.equal(mute,false);assert.equal(vol,50);assert.equal(soundVideo.muted,false);assert.equal(soundVideo.volume,.5);vol=20;soundVideo.volume=.2;quality.setSound(soundPlayer,soundVideo,true);assert.equal(vol,20);assert.equal(soundVideo.volume,.2);quality.setSound(soundPlayer,soundVideo,false);assert(mute&&soundVideo.muted);assert(quality.setSound({setMute(){throw Error("not ready");}},soundVideo,true));assert.equal(soundVideo.muted,false);console.log("PASS: player mute and zero-volume recovery, existing level preservation, explicit mute and unavailable JW fallback.");

// Explicit source level adjusts media gain, never Samsung's system volume.
assert.equal(quality.sourceVolume(soundPlayer,soundVideo),20);
for(const level of [50,75,100]){assert(quality.setSourceVolume(soundPlayer,soundVideo,level));assert.equal(vol,level);assert.equal(soundVideo.volume,level/100);assert.equal(mute,false);assert.equal(soundVideo.muted,false);}
for(const level of [-1,0,51,150,NaN,'100'])assert(!quality.setSourceVolume(soundPlayer,soundVideo,level));
assert.equal(vol,100);assert(quality.setSourceVolume({setVolume(){throw Error('unready')}},soundVideo,75));assert.equal(soundVideo.volume,.75);assert(!quality.setSourceVolume(null,null,100));assert.equal(quality.sourceVolume(null,null),null);
console.log('PASS: explicit 50/75/100 source levels, mute recovery, invalid-level rejection and unavailable player fallback.');
