/* Native FlixTor remains the sole autoplay scheduler and progress writer. */
var FTV_NEXT=(function(){
  function attach(parent,readEpisodes){
    var root=document.createElement('div');root.id='ftv-next-episode';root.style.cssText='position:absolute;right:3vw;bottom:12vh;z-index:2147483200;background:#101820f5;padding:1em;border-radius:14px;color:white;font:clamp(22px,1.7vw,44px) Arial;display:none';
    var title=document.createElement('p'),play=document.createElement('button');play.type='button';play.style.cssText='font:inherit;padding:.7em 1em;background:#b9ef83;border:3px solid white;border-radius:10px';root.appendChild(title);root.appendChild(play);parent.appendChild(root);
    // Cache inputs, not time: readEpisodes also scans all native history records.
    var target=null,dirty=true,cachedKey='',locked='',attemptAt=0,currentKey='',observer=null;
    function current(){var row=document.querySelector('.eplist.table-active');return row?{season:Number(row.getAttribute('data-pes')),number:Number(row.getAttribute('data-pep'))}:null;}
    function key(c){return c?c.season+':'+c.number:'';}
    function videoFocus(){var v=parent.querySelector('video');if(v){v.tabIndex=-1;v.focus();}}
    function hide(){if(document.activeElement===play)videoFocus();root.style.display='none';}
    function next(c){if(!arguments.length)c=current();var k=key(c);if(dirty||cachedKey!==k){target=c?FTV_HISTORY.next(readEpisodes(),c):null;cachedKey=k;dirty=false;}return target;}
    function pending(k){if(locked&&(locked!==k||Date.now()-attemptAt>=4000))locked='';return !!locked&&locked===k;}
    function advance(expected){
      var c=current(),k=key(c);if(typeof expected==='string'&&expected!==k)return false;
      if(pending(k))return false;var ep=next(c);
      if(!ep||!ep.native||typeof ep.native.click!=='function')return false;
      // Native autoplay can replace the active row while the target is being read.
      if(key(current())!==k){dirty=true;return false;}
      locked=k;attemptAt=Date.now();hide();
      try{ep.native.click();}catch(error){locked='';tick();return false;}
      return true;
    }
    function episodeNode(node){while(node&&node!==document){if(node.nodeType===1){if((' '+node.className+' ').indexOf(' eplist ')!==-1)return true;}node=node.parentNode;}return false;}
    function containsEpisode(node){return episodeNode(node)||!!(node&&node.querySelector&&node.querySelector('.eplist'));}
    if(typeof MutationObserver==='function'&&document.documentElement){observer=new MutationObserver(function(changes){for(var i=0;i<changes.length;i++){var change=changes[i];if(episodeNode(change.target)){dirty=true;return;}var nodes=[].slice.call(change.addedNodes||[]).concat([].slice.call(change.removedNodes||[]));for(var j=0;j<nodes.length;j++)if(containsEpisode(nodes[j])){dirty=true;return;}}});observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class','data-pes','data-pep','data-pid']});}
    function tick(){var c=current(),k=key(c);currentKey=k;target=next(c);var v=parent.querySelector('video'),remaining=v&&isFinite(v.duration)?Math.max(0,Math.ceil(v.duration-v.currentTime)):Infinity;var show=target&&v&&(v.ended||remaining<=30)&&!pending(k);if(show){root.style.display='block';var toggle=document.querySelector('#autoplay-toggle');title.textContent='Next: S'+target.season+' · E'+target.number+' · '+target.title+(toggle&&toggle.checked&&!v.ended?' · starts in '+remaining+'s':'');play.textContent='▶ Play next episode';}else hide();var jw=parent.querySelector('#player.jwplayer');if(jw&&root.parentNode!==jw)jw.appendChild(root);}
    play.addEventListener('click',function(e){e.stopPropagation();advance(currentKey);});var timer=setInterval(tick,500);tick();
    return {next:next,advance:advance,handleKey:function(e){if(root.style.display==='none')return false;var k=e.keyCode;if((k===40||e.key==='ArrowDown')&&document.activeElement!==play){play.focus();return true;}if(document.activeElement===play){if(k===13||e.key==='Enter'){advance(currentKey);return true;}if(k===38||e.key==='ArrowUp'||k===10009||e.key==='Escape'){videoFocus();return true;}}return false;},destroy:function(){clearInterval(timer);if(observer)observer.disconnect();hide();root.remove();}};
  }
  return {attach:attach};
}());
