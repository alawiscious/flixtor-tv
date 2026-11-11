// Focus regressions: asynchronous recommendation responses must not interrupt another task.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/src/app.js','utf8');
const code=source.slice(source.indexOf('  function profileChooser(){'),source.indexOf('  function sourcePagination()'));
assert(code.includes('function loadRecommendations()'));
function fixture(){
  let request,context;
  const created=[];
  function element(tag,cls,text){return {tagName:String(tag).toUpperCase(),className:cls||'',textContent:text||'',children:[],isConnected:true,appendChild(child){this.children.push(child);child.parentNode=this;return child;},querySelector(selector){const nodes=[];function collect(n){n.children.forEach(c=>{nodes.push(c);collect(c);});}collect(this);if(selector==='.choice-row button')return nodes.find(n=>n.tagName==='BUTTON'&&n.parentNode.className==='choice-row')||null;return nodes.find(n=>n.tagName==='BUTTON')||null;},remove(){this.isConnected=false;},contains(node){return this===node||this.children.some(c=>c.contains(node));}};}
  function allButtons(root){let result=[];(root.children||[]).forEach(c=>{if(c.tagName==='BUTTON')result.push(c);result.push(...allButtons(c));});return result;}
  context={preview:false,localShell:true,profilePacks:[],selectedProfile:'',profileRequest:null,profilePrompted:false,pendingClose:false,
    recommendationState:'idle',connectRecommendations:true,tab:'Home',dialog:null,detailItem:null,bridgeOrigin:'http://fixture',
    document:{activeElement:{tagName:'BUTTON'}},sessionStorage:{setItem(){}},
    node:element,append(parent,...children){children.forEach(c=>parent.appendChild(c));return parent;},
    row(parent,cls){return parent.appendChild(element('div',cls));},
    button(text,fn,cls){let b=element('button',cls,text);b.click=fn;return b;},
    startDialog(title){if(context.dialog)context.dialog.isConnected=false;const d=element('div','overlay');d.title=title;context.dialog=d;const wrap=d.appendChild(element('div','detail-wrap'));wrap.appendChild(context.button('← Back',()=>{}));created.push(d);return wrap;},
    focus(el){if(el)context.document.activeElement=el;},preserveRender(){},render(){},useRecommendationPack(pack){context.lastPack=pack;},
    main:{querySelector(){return {tagName:'BUTTON'};}},
    XMLHttpRequest:function(){request=this;this.open=()=>{};this.send=()=>{};}
  };
  vm.createContext(context);vm.runInContext(code,context);
  function manualRequest(){context.profileChooser();const load=allButtons(context.dialog).find(b=>b.textContent==='Load profiles');assert(load,'Load profiles control exists');load.click();return context.dialog;}
  function respond(){request.status=200;request.responseText=JSON.stringify({engine:'gorse',items:[],profiles:[{id:'viewer-a',name:'Example viewer',items:[]}]});request.onload();}
  return {context,manualRequest,respond,get request(){return request;},created,allButtons};
}
{
  const f=fixture(),owner=f.manualRequest();owner.isConnected=false;const unrelated={isConnected:true,title:'Genre filter'};f.context.dialog=unrelated;f.respond();
  assert.equal(f.context.dialog,unrelated,'A completed profile request must not replace a different open dialog');
  assert.equal(f.created.length,1,'A stale response must not reopen the chooser');
}
{
  const f=fixture();f.manualRequest();f.request.onerror();assert(!f.context.profileRequest,'Failed request clears pending chooser intent');
  f.context.dialog=null;f.context.tab='Search';f.context.loadRecommendations();f.respond();
  assert.equal(f.context.dialog,null,'Later background success must not revive a failed chooser request');
}
{
  const f=fixture();f.context.loadRecommendations();f.context.tab='Search';f.respond();
  assert.equal(f.context.dialog,null,'First background response must not interrupt Search');
  assert.equal(f.created.length,0);
}
{
  const f=fixture();f.context.loadRecommendations();f.respond();
  assert.equal(f.created.length,1,'An unchanged first Home load can offer profile selection');
}
{
  const f=fixture();f.manualRequest();f.respond();
  assert(f.allButtons(f.context.dialog).some(b=>b.textContent==='Example viewer'),'An active user-requested chooser should populate successfully');
}
{
  const f=fixture();f.manualRequest();f.context.pendingClose=true;f.respond();
  assert.equal(f.created.length,1,'Completing a request while Back is closing its owner must not reopen it');
}
console.log('PASS: stale/failed profile requests, Search navigation, first Home prompt, active request success and closing-dialog race.');
