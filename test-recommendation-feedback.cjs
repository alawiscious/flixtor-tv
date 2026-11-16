const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/src/app.js','utf8');
const code=source.slice(source.indexOf('  function showRecommendation('),source.indexOf('  function readEpisodes('));
function fixture(){
 const controls=[],requests=[];
 function el(tag,cls,text){return {textContent:text||'',dataset:{},children:[],classList:{toggle(){}},setAttribute(k,v){this[k]=v;},appendChild(c){this.children.push(c);if(!this.firstChild)this.firstChild=c;return c;}};}
 const item={title:'Example series',url:'/tv/42',profileId:'alec',feedback:{}};
 const context={main:{querySelector(){return null;}},preserveRender(){context.renders=(context.renders||0)+1;},document:{activeElement:null},lastRecommendationBundle:null,profilePacks:[],returnFocus:null,dialog:{},recommendationsDirty:false,connectRecommendations:true,selectedProfile:'alec',bridgeOrigin:'http://fixture',episodeContext:{profileId:'alec',titles:{}},recommendations:[{...item,title:'First',url:'/tv/41'},item,{...item,title:'Last',url:'/tv/43'}],
  startDialog(){return el();},node:el,row(parent,cls){return parent.appendChild(el('div',cls));},append(p,...cs){cs.forEach(c=>p.appendChild(c));},
  button(label,fn){const b=el('button','',label);b.click=()=>{context.document.activeElement=b;fn();};controls.push(b);return b;},focus(b){context.document.activeElement=b;},
  RATING_OPTIONS:[['love','Loved it'],['like','Liked it'],['dislike','Didn\u2019t like it'],['hate','Hated it']],RATING_VALUES:['love','like','dislike','hate'],
  meta(){return el();},tv(){return true;},pid(){return '42';},itemKey(i){return i.url;},
  XMLHttpRequest:function(){requests.push(this);this.open=()=>{};this.setRequestHeader=()=>{};this.send=p=>{this.payload=JSON.parse(p);};}
 };
 vm.createContext(context);vm.runInContext(code,context);context.showRecommendation(item,{});
 const click=label=>controls.find(b=>b.textContent===label).click();
 function respond(n,state){requests[n].status=200;requests[n].responseText=JSON.stringify({saved:true,state});requests[n].onload();}
 return {context,controls,requests,item,click,respond};
}
{
 const f=fixture();f.click('Good recommendation');const focused=f.context.document.activeElement;
 assert(!focused.disabled);f.respond(0,{preference:'like',watched:null});
 assert.equal(f.context.document.activeElement,focused,'Saving keeps focus on Good recommendation');
 assert.deepEqual(Array.from(f.context.recommendations,i=>i.title),['First','Example series','Last'],'A like must not reorder the row');
 f.click('Already watched');f.respond(1,{preference:'like',watched:true});
 assert.equal(f.item.feedback.watched,true);assert.equal(f.item.feedback.preference,'like');
 assert.deepEqual(Array.from(f.context.recommendations,i=>i.title),['First','Last'],'Watched title is removed, remaining order is stable');
 // The confirmed choice reaches the shared watched map at once, and clearing it removes only an own choice.
 assert.deepEqual(JSON.parse(JSON.stringify(f.context.episodeContext.watched)),{'flixtor:tv:42':{watched:true,source:'manual'}});
 f.context.episodeContext.watched['flixtor:tv:7']={watched:true,source:'netflix'};
 f.click('Already watched');f.respond(2,{preference:'like',watched:null});
 assert.deepEqual(JSON.parse(JSON.stringify(f.context.episodeContext.watched)),{'flixtor:tv:7':{watched:true,source:'netflix'}});
}
{
 const f=fixture();f.click('Good recommendation');f.click('Already watched');
 assert.equal(f.requests.length,1,'Rapid choices serialize writes');
 assert.equal(f.item.feedback.watched,true,'Pending watch choice is shown immediately');
 f.respond(0,{preference:'like',watched:null});assert.equal(f.requests.length,2);
 assert.equal(f.requests[1].payload.preference,'like');assert.equal(f.requests[1].payload.watched,true);
 assert.equal(f.item.feedback.watched,true,'Older response cannot undo a pending choice');
 f.respond(1,{preference:'like',watched:true});assert.equal(f.context.document.activeElement.textContent,'Already watched');
}
{
 const f=fixture();f.click('Good recommendation');f.requests[0].onerror();
 assert(!f.item.feedback.preference,'Failed optimistic choice rolls back');
 assert.equal(f.context.recommendations.length,3,'Failure retains title');
 f.click('Already watched');assert.equal(f.requests.length,2,'Failure permits retry');
}
{
 const f=fixture();f.click('Already watched');f.context.dialog=null;
 f.respond(0,{preference:'clear',watched:true});
 assert.equal(f.context.recommendations.length,2,'Closing during save still removes the watched title');
 assert.equal(f.context.renders,1,'A completed save refreshes the visible row if the dialog already closed');
}
{
 // Seen + rating: the payload carries the rating; the server's answer (rating implies watched) is the truth.
 const f=fixture();f.click('Loved it');
 assert.equal(f.requests[0].payload.rating,'love');assert.equal(f.requests[0].payload.preference,'clear');
 f.respond(0,{preference:'clear',watched:true,rating:'love'});
 assert.equal(f.item.feedback.rating,'love');assert.equal(f.item.feedback.watched,true);
 assert.deepEqual(Array.from(f.context.recommendations,i=>i.title),['First','Last'],'A rated (seen) title leaves the picks');
}
{
 const f=fixture();f.item.feedback={rating:'hate',watched:true};f.click('Hated it');
 assert.strictEqual(f.requests[0].payload.rating,null,'Selecting the chosen rating again clears it (null, not "clear")');
}
console.log('PASS: feedback focus, stable row order, rapid combined choices, stale response protection, watched removal, failed-save retry and seen + rating (love/like/dislike/hate) payloads.');
