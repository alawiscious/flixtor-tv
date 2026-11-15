// Home hero layout with long titles at TV resolutions, in headless Chrome over the offline preview
// (sample catalogue, no network). Chrome layout only; the Samsung browser still needs a TV check.
'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const {launch,openPage,sleep}=require('./browser-harness.cjs');
const bundle=require('./bundle.cjs').appBundle(__dirname);
const sample=fs.readFileSync(__dirname+'/preview/sample.js','utf8');

const CASES={
  'long title':{title:'The Lord of the Rings: The Rings of Power',meta:'Action, Adventure, Drama, Sci-Fi & Fantasy',description:'Beginning in a time of relative peace, an ensemble cast of characters confronts the re-emergence of evil to Middle-earth, from the darkest depths of the Misty Mountains to the majestic forests of Lindon.'},
  'stress: longer metadata and synopsis':{title:'The Lord of the Rings: The Rings of Power — Season Two Extended Edition',meta:'Action, Adventure, Drama, Sci-Fi & Fantasy, War, Family, History, Mystery',description:'Beginning in a time of relative peace, an ensemble cast of characters confronts the re-emergence of evil to Middle-earth. '.repeat(4)}
};
const SIZES=[[1280,720],[1920,1080],[3840,2160]];
const page=c=>'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FlixTor TV</title></head><body><script>'+sample+'</script><script>Object.assign(window.FTV_PREVIEW[0],'+JSON.stringify(c)+');</script><script>'+bundle.replace(/<\/script/gi,'<\\/script')+'</script></body></html>';

const MEASURE=`(function(){var h=document.querySelector('#ftv .hero'),r=function(e){var b=e.getBoundingClientRect();return {top:b.top,bottom:b.bottom,left:b.left,right:b.right};};
  var copy=h.querySelector('.hero-copy'),actions=h.querySelector('.actions'),h1=h.querySelector('h1'),syn=h.querySelector('.synopsis'),next=h.nextElementSibling;
  var lh=parseFloat(getComputedStyle(syn).lineHeight);
  return {hero:r(h),copy:r(copy),actions:r(actions),buttons:Array.prototype.map.call(actions.querySelectorAll('button'),r),next:next&&r(next),
    h1Overflow:h1.scrollWidth-h1.clientWidth,h1Size:parseFloat(getComputedStyle(h1).fontSize),synLines:Math.round(syn.getBoundingClientRect().height/lh)};}())`;

(async()=>{
  const cdp=await launch();const failures=[];
  try{
    for(const [name,c] of Object.entries(CASES))for(const [w,hgt] of SIZES){
      const label=name+' @ '+w+'x'+hgt;
      const p=await openPage(cdp,'https://preview.ftv.test/',u=>u==='https://preview.ftv.test/'?page(c):null);
      try{
        await p.send('Emulation.setDeviceMetricsOverride',{width:w,height:hgt,deviceScaleFactor:1,mobile:false});
        await p.navigate();for(let i=0;i<100&&!(await p.evaluate('!!document.querySelector("#ftv .hero h1")').catch(()=>false));i++)await sleep(50);
        await sleep(400);
        const m=await p.evaluate(MEASURE),tol=1;
        assert(m.copy.bottom<=m.hero.bottom+tol,'hero copy overflows hero ('+Math.round(m.copy.bottom-m.hero.bottom)+'px)');
        m.buttons.forEach((b,i)=>assert(b.bottom<=m.hero.bottom+tol&&b.right<=m.hero.right+tol,'hero action '+(i+1)+' clipped by hero bounds'));
        assert(!m.next||m.next.top>=m.hero.bottom-tol,'next section starts inside the hero');
        assert(m.h1Overflow<=1,'hero title overflows horizontally');
        assert(m.synLines<=2,'synopsis shows '+m.synLines+' lines (max 2)');
        // Remote: into the next rail, open details, Back restores the same card.
        await p.evaluate('(function(){var b=document.querySelector("#ftv .hero .actions button");b.focus();return true;}())');
        await p.key('ArrowDown');await sleep(150);
        const card=await p.evaluate('(function(){var a=document.activeElement;return a&&a.dataset.item&&!a.closest(".hero")?a.dataset.item:null;}())');
        assert(card,'ArrowDown from hero actions reaches a rail card');
        await p.key('Enter');await sleep(500);assert(await p.evaluate('!!document.querySelector("#ftv .overlay")'),'Enter opens details');
        await p.key('Escape');await sleep(500);
        assert.equal(await p.evaluate('document.activeElement&&document.activeElement.dataset.item||null'),card,'Back restores focus to the card');
        console.log('  ok  '+label+' (title '+m.h1Size+'px, hero '+Math.round(m.hero.bottom-m.hero.top)+'px tall)');
      }catch(e){failures.push(label);console.log('  FAIL '+label+'\n       '+e.message.split('\n')[0]);}finally{await p.close();}
    }
  }finally{cdp.close();}
  if(failures.length){console.log('FAIL: '+failures.length+' hero layout case(s).');process.exit(1);}
  console.log('PASS: Home hero long-title layout at 720p/1080p/4K (bounds, rail spacing, title wrap, 2-line synopsis, rail navigation, details and Back focus). Chrome only; Samsung layout needs a TV check.');
})().catch(e=>{console.error(e);process.exit(1);});
