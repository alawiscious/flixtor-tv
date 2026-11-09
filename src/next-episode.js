/* Native FlixTor remains the sole autoplay scheduler and progress writer. */
var FTV_NEXT=(function(){
  function attach(parent,readEpisodes){
    var root=document.createElement('div');root.id='ftv-next-episode';root.style.cssText='position:absolute;right:3vw;bottom:12vh;z-index:2147483200;background:#101820f5;padding:1em;border-radius:14px;color:white;font:clamp(22px,1.7vw,44px) Arial;display:none';
    var title=document.createElement('p'),play=document.createElement('button');play.type='button';play.style.cssText='font:inherit;padding:.7em 1em;background:#b9ef83;border:3px solid white;border-radius:10px';root.appendChild(title);root.appendChild(play);parent.appendChild(root);
    var target=null,locked='',currentKey='';
    function current(){var row=document.querySelector('.eplist.table-active');return row?{season:Number(row.getAttribute('data-pes')),number:Number(row.getAttribute('data-pep'))}:null;}
    function next(){var c=current();return c?FTV_HISTORY.next(readEpisodes(),c):null;}
    function advance(expected){var c=current(),key=c?c.season+':'+c.number:'';var ep=next();if(typeof expected==='string'&&expected!==key)return false;if(!ep||!ep.native||locked===key)return false;locked=key;root.style.display='none';ep.native.click();return true;}
    function tick(){var c=current(),key=c?c.season+':'+c.number:'';if(key!==currentKey){currentKey=key;locked='';}target=next();var v=parent.querySelector('video'),remaining=v&&isFinite(v.duration)?Math.max(0,Math.ceil(v.duration-v.currentTime)):Infinity;var show=target&&v&&(v.ended||remaining<=30)&&locked!==key;root.style.display=show?'block':'none';if(show){var toggle=document.querySelector('#autoplay-toggle');title.textContent='Next: S'+target.season+' · E'+target.number+' · '+target.title+(toggle&&toggle.checked&&!v.ended?' · starts in '+remaining+'s':'');play.textContent='▶ Play next episode';}var jw=parent.querySelector('#player.jwplayer');if(jw&&root.parentNode!==jw)jw.appendChild(root);}
    play.addEventListener('click',function(e){e.stopPropagation();advance(currentKey);});var timer=setInterval(tick,500);tick();
    return {next:next,advance:advance,handleKey:function(e){if(root.style.display==='none')return false;var k=e.keyCode;if((k===40||e.key==='ArrowDown')&&document.activeElement!==play){play.focus();return true;}if(document.activeElement===play){if(k===13||e.key==='Enter'){advance(currentKey);return true;}if(k===38||e.key==='ArrowUp'||k===10009||e.key==='Escape'){var v=parent.querySelector('video');if(v){v.tabIndex=-1;v.focus();}return true;}}return false;},destroy:function(){clearInterval(timer);root.remove();}};
  }
  return {attach:attach};
}());
