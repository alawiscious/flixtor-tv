/* Public synopsis collection. Only native information popups are fetched;
 * never load a player or copy account/session credentials to the Mac. */
var FTV_PLOTS=(function(){
  var shell=(window.FTV_BRIDGE_ORIGIN||'http://127.0.0.1:8773')+'/tv';
  function key(text){return String(text||'').toLowerCase().replace(/[^a-z0-9]/g,'');}
  function parse(html,item){
    var doc=new DOMParser().parseFromString(html,'text/html');
    var title=doc.querySelector('.poptitle'),plot=doc.querySelector('.d-flex.mt-1.mx-2.t12');
    var text=plot&&plot.textContent.replace(/\s+/g,' ').trim();
    if(!title||key(title.textContent)!==key(item.title)||!text||text.length<40||text.length>2000)return null;
    return {id:item.id,title:item.title,year:item.year,description:text};
  }
  function collector(){
    if(location.hostname!=='flixtor.to'||location.pathname!=='/home'||location.hash.indexOf('#ftv-collect=')!==0)return false;
    var items;try{items=JSON.parse(decodeURIComponent(location.hash.slice(13)));}catch(_){items=[];}
    if(!Array.isArray(items)||items.length>32||!items.every(function(i){return i&&/^flixtor:(movie|tv):\d+$/.test(i.id)&&typeof i.title==='string'&&typeof i.year==='string';}))items=[];
    function start(){
      var cover=document.createElement('div');cover.id='ftv-plot-collector';cover.style.cssText='position:fixed;inset:0;z-index:2147483647;background:#090d12;color:#fff;padding:8vh 8vw;font:clamp(24px,2vw,48px) Arial;box-sizing:border-box';
      var title=document.createElement('h1');title.textContent='Gathering story descriptions';cover.appendChild(title);
      var note=document.createElement('p');note.textContent='Reading FlixTor information panels. Your current recommendations stay available.';cover.appendChild(note);
      var status=document.createElement('p');status.setAttribute('role','status');cover.appendChild(status);
      var stop=document.createElement('button');stop.textContent='Stop and save progress';stop.style.cssText='font:inherit;padding:20px;background:#273a4d;color:white;border:3px solid #b9ef83';cover.appendChild(stop);document.body.appendChild(cover);stop.focus();
      var at=0,rows=[],failed=[],stopped=false,done=false,request=null,timer;
      function finish(){if(done)return;done=true;clearTimeout(timer);if(request)request.abort();location.replace(shell+'#'+encodeURIComponent(JSON.stringify({path:'/home',items:[],plotBatch:{rows:rows,failed:failed},collectMore:!stopped})));}
      function next(){
        if(stopped||at>=items.length){finish();return;}
        var item=items[at++],match=item.id.match(/^flixtor:(movie|tv):(\d+)$/);
        status.textContent=at+' of '+items.length+' in this batch · '+item.title;
        request=new XMLHttpRequest();request.open('GET','/ajax/info/'+(match[1]==='tv'?'t':'m')+'/'+match[2]);request.timeout=8000;
        function complete(row){if(done)return;if(row)rows.push(row);else failed.push(item.id);timer=setTimeout(next,500);}
        request.onload=function(){var row=null;try{if(request.status===200)row=parse(request.responseText,item);}catch(_){}complete(row);};
        request.onerror=request.ontimeout=function(){complete(null);};request.send();
      }
      stop.onclick=function(){stopped=true;finish();};
      document.addEventListener('keydown',function(e){if(e.keyCode===10009||e.key==='Escape'||e.key==='BrowserBack'){e.preventDefault();e.stopImmediatePropagation();stopped=true;finish();}else if(e.key==='Enter'||e.keyCode===13){e.preventDefault();stopped=true;finish();}},true);
      next();
    }
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();return true;
  }
  function launch(items){location.assign('https://flixtor.to/home#ftv-collect='+encodeURIComponent(JSON.stringify(items)));}
  return {collector:collector,launch:launch,parse:parse};
}());
