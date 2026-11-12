const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync(__dirname+'/src/app.js','utf8');
function fixture(){
 let request;
 const c={URL,preview:false,localShell:false,all:[],sourceTitle:()=>({url:'https://flixtor.to/watch/tv/42/example',title:'Example',meta:''}),itemKey:i=>i.url.match(/\/watch\/(tv|movie)\/\d+/)[0],tokens:i=>(i.meta||'').split(',').map(s=>s.trim()).filter(Boolean),tv:i=>i.url.includes('/tv/'),similarSeed:null,tab:'Home',render(){c.rendered=(c.rendered||0)+1;},focus(){},main:{querySelector(){}},nav:{querySelector(){}},rememberView(){},titleNavigation:(item,mode)=>item.url+'#ftv-'+mode,location:{origin:'http://127.0.0.1:8773',assign:url=>c.assigned=url},sessionStorage:{removeItem:key=>c.cleared=key},toast:message=>{c.error=message;},XMLHttpRequest:function(){request=this;this.open=(...args)=>{this.args=args;};this.send=()=>{};}};
 vm.createContext(c);vm.runInContext(app.slice(app.indexOf('  function similar(seed){'),app.indexOf('  function startDialog(')),c);
 vm.runInContext(app.slice(app.indexOf('  function navigateCatalogue('),app.indexOf('  function gotoRoute(')),c);
 return {c,get request(){return request;}};
}
{
 const {c}=fixture(),seed=c.sourceTitle();c.all=[seed,...Array.from({length:12},(_,n)=>({url:'https://flixtor.to/watch/tv/'+(100+n)+'/related',title:'Related '+n,meta:'Drama'}))];
 assert.equal(c.similar(seed).length,12,'Native related titles work even when the selected title has no genre metadata');
 c.showSimilar(seed);assert.equal(c.similarSeed,seed);assert.equal(c.tab,'Series');assert.equal(c.rendered,1);
}
{
 const {c}=fixture();c.localShell=true;const seed=c.sourceTitle();c.showSimilar(seed);assert.equal(c.assigned,seed.url+'#ftv-similar','Catalogue More like this loads native related titles, rather than matching the current page');
}
{
 const f=fixture();f.c.localShell=true;f.c.navigateCatalogue('https://flixtor.to/show/tvshows');
 assert.equal(f.request.args[1],'http://127.0.0.1:8773/updates/runtime');assert(!f.c.assigned);
 const envelope={manifest:{version:'example'},payload:'signed runtime bytes'};f.request.status=200;f.request.responseText=JSON.stringify(envelope);f.request.onload();
 const target=new URL(f.c.assigned),data=JSON.parse(decodeURIComponent(target.hash.slice('#ftv-runtime='.length)));
 assert.equal(target.pathname,'/show/tvshows');assert.equal(data.hash,'#ftv-return');assert.deepEqual(data.envelope,envelope);
 assert.equal(f.c.cleared,'ftv.original.v1');
}
{
 const f=fixture();f.c.localShell=true;f.c.navigateCatalogue('https://flixtor.to/show/tvshows');f.request.ontimeout();assert.equal(f.c.assigned,'https://flixtor.to/show/tvshows#ftv-return','Bridge failure falls back to a bounded native transition without declaring original mode');
}
{
 const f=fixture();f.c.navigateCatalogue('https://example.com/show/tvshows');assert(!f.c.assigned);assert(f.c.error);
}
console.log('PASS: metadata-free native related titles, catalogue-to-related navigation, signed Series handoff, bounded fallback and route validation.');

{
 const c={window:{FTV_BRIDGE_ORIGIN:'http://127.0.0.1:8773'},location:{pathname:'/show/tvshows',href:'https://flixtor.to/show/tvshows?genre=Drama',replace:url=>c.handoff=url},all:[{title:'Series source title',url:'https://flixtor.to/watch/tv/42/example'}],list:()=>[],document:{querySelector:()=>null},FTV_HISTORY:{loadWatching(){throw Error('Catalogue navigation must not wait for history');}}};
 vm.createContext(c);vm.runInContext(app.slice(app.indexOf('  function sourceHandoff(){'),app.indexOf('  var preview =')),c);c.sourceHandoff();
 const payload=JSON.parse(decodeURIComponent(new URL(c.handoff).hash.slice(1)));assert.equal(payload.path,'/show/tvshows');assert.equal(payload.items.length,1);
}
console.log('PASS: Series catalogue handoff stays in TV shell and skips the separate history request.');
