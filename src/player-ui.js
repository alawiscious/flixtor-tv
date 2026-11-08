/* Remote-friendly controls around the existing player; no stream or progress replacement. */
var FTV_PLAYER_UI=(function(){
  function attach(parent,getPlayer){
    var old=document.getElementById('ftv-player-controls');if(old)old.remove();
    var root=document.createElement('div');root.id='ftv-player-controls';
    var style=document.createElement('style');style.textContent='#ftv-player-controls{position:absolute;top:3vh;right:3vw;z-index:2147483200;color:#fff;font:24px Arial;font-size:clamp(22px,1.6vw,48px)}#ftv-player-controls button{font:inherit;color:#fff;background:#172433;border:2px solid #728297;border-radius:10px;padding:.55em .9em;cursor:pointer}#ftv-player-controls button:focus{outline:4px solid #b9ef83;outline-offset:4px;background:#314839}#ftv-player-controls .ftv-player-panel{background:#101820f5;padding:1.2em;border:2px solid #71819b;border-radius:14px;max-height:82vh;overflow:auto;width:30vw;min-width:320px;max-width:760px;box-shadow:0 10px 50px #000a}#ftv-player-controls h2{font:inherit;font-weight:bold;margin:0 0 1em}#ftv-player-controls .ftv-player-panel button{display:block;width:100%;text-align:left;margin:.55em 0}#ftv-player-controls p{line-height:1.5}';root.appendChild(style);
    var trigger=document.createElement('button');trigger.type='button';trigger.textContent='⚙ Settings';trigger.setAttribute('aria-label','Player settings');root.appendChild(trigger);parent.appendChild(root);root.addEventListener('click',function(e){e.stopPropagation();});
    var panel=null,kind='Settings';
    function focus(el){if(el){el.focus();if(el.scrollIntoView)el.scrollIntoView({block:'nearest'});}}
    function add(label,fn,selected){var b=document.createElement('button');b.type='button';b.textContent=(selected?'✓ ':'')+label;b.addEventListener('click',fn);if(selected!==undefined){b.setAttribute('role','menuitemradio');b.setAttribute('aria-checked',String(selected));}panel.appendChild(b);return b;}
    function close(){if(panel){panel.remove();panel=null;trigger.style.display='';trigger.setAttribute('aria-expanded','false');focus(trigger);return true;}return false;}
    function open(next){
      kind=next||'Settings';if(panel)panel.remove();trigger.style.display='none';trigger.setAttribute('aria-expanded','true');panel=document.createElement('div');panel.className='ftv-player-panel';panel.setAttribute('role','dialog');panel.setAttribute('aria-label',kind);panel.setAttribute('aria-modal','true');root.appendChild(panel);
      var title=document.createElement('h2');title.textContent=kind;panel.appendChild(title);
      add(kind==='Settings'?'Close settings':'← Settings',function(){if(kind==='Settings')close();else open('Settings');});
      var player;try{player=getPlayer();}catch(_){}
      if(kind==='Settings'){add('Subtitles',function(){open('Subtitles');});add('Quality',function(){open('Quality');});}
      else if(player){
        try{
          var captions=kind==='Subtitles',items=captions?player.getCaptionsList():player.getQualityLevels(),current=captions?player.getCurrentCaptions():player.getCurrentQuality();
          if(captions&&!items.length)items=[{label:'Off'}];
          items.forEach(function(item,index){var label=captions&&index===0?'Off':item.label||('Track '+index);add(label,function(){try{if(captions)player.setCurrentCaptions(index);else player.setCurrentQuality(index);open(kind);}catch(_){message('This setting is not ready. Try again shortly.');}},index===current);});
          if(!items.length)message('Options will appear when the video is ready.');
        }catch(_){message('Options will appear when the video is ready.');}
      }else message('Options will appear when the video is ready.');
      focus(panel.querySelector('[aria-checked="true"]')||panel.querySelector('button'));
    }
    function message(text){var p=document.createElement('p');p.textContent=text;panel.appendChild(p);}
    trigger.addEventListener('click',function(){open('Settings');});trigger.setAttribute('aria-expanded','false');
    function gearClick(e){var target=e.target.closest&&e.target.closest('.jw-icon-settings,.jw-icon-cc,.jw-settings-submenu-button');if(!target||!parent.contains(target)||root.contains(target))return;if(target.classList.contains('jw-settings-submenu-button'))return;e.preventDefault();e.stopImmediatePropagation();open(target.classList.contains('jw-icon-cc')?'Subtitles':'Settings');}
    document.addEventListener('click',gearClick,true);
    function handleKey(e){
      var code=e.keyCode,key=e.key,active=document.activeElement;
      var back=code===10009||key==='Escape'||key==='BrowserBack';
      if(panel){
        if(back){if(kind==='Settings')close();else open('Settings');return true;}
        if(code===13||key==='Enter'){if(panel.contains(active)&&active.tagName==='BUTTON')active.click();return true;}
        if([37,38,39,40].indexOf(code)!==-1||/^Arrow/.test(key)||key==='Tab'){
          var buttons=Array.prototype.slice.call(panel.querySelectorAll('button')),at=buttons.indexOf(active),delta=code===37||code===38||key==='ArrowLeft'||key==='ArrowUp'||e.shiftKey?-1:1;
          focus(buttons[(at+delta+buttons.length)%buttons.length]);return true;
        }return true;
      }
      if((code===38||key==='ArrowUp')&&!root.contains(active)){focus(trigger);return true;}
      if(root.contains(active)){
        if(code===13||key==='Enter'){trigger.click();return true;}
        if(code===40||key==='ArrowDown'){var video=parent.querySelector('video');focus(video||parent);return true;}
      }
      if((code===13||key==='Enter')&&active&&parent.contains(active)&&active.matches('[role="button"],button')){active.click();return true;}
      return false;
    }
    return {handleKey:handleKey,close:close,destroy:function(){document.removeEventListener('click',gearClick,true);root.remove();}};
  }
  return {attach:attach};
}());
