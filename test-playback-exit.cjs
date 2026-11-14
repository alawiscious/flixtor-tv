// Unit coverage for the playback-exit helpers plus source contracts for app.js. The lifecycle
// itself runs in real Chrome via test-playback-exit-browser.cjs; neither establishes Samsung behavior.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ctx={Date};vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/src/playback-exit.js','utf8'),ctx);
const X=ctx.FTV_PLAYBACK_EXIT;

// Teardown steps are isolated: one throwing step cannot strand the details page.
{const ran=[];assert.equal(X.run([()=>ran.push('a'),()=>{throw Error('boom');},()=>ran.push('c')]),1);assert.deepEqual(ran,['a','c']);}

// Pausing goes through the player API; the element is touched only if the player did not pause it.
{const calls=[];const video={paused:false,pause(){calls.push('element');this.paused=true;}};
 X.pausePlayer({getState:()=>'playing',pause(force){calls.push('api:'+force);video.paused=true;}},video);assert.deepEqual(calls,['api:true']);
 calls.length=0;video.paused=false;X.pausePlayer({getState:()=>'playing',pause(){calls.push('api');}},video);assert.deepEqual(calls,['api','element'],'fallback when the player ignores pause');
 calls.length=0;video.paused=true;X.pausePlayer({getState:()=>'paused',pause(){calls.push('api');}},video);assert.deepEqual(calls,[],'already paused: no calls');
 calls.length=0;video.paused=false;X.pausePlayer(null,video);assert.deepEqual(calls,['element'],'no player API');
 X.pausePlayer({getState(){throw Error('not ready');},pause(){throw Error('x');}},null);}

// A video that restarts on every pause (the ping-pong hazard) gets bounded pauses, one stop, then quiet.
{let t=0,pauses=0,stops=0;const guard=X.pauseGuard({isActive:()=>true,now:()=>t,pause:()=>pauses++,stop:()=>stops++});
 const video={tagName:'VIDEO'};for(let i=0;i<1000;i++){t+=2;guard.onPlay({target:video});}
 assert.equal(pauses,4,'bounded pauses');assert.equal(stops,1,'escalates exactly once');assert(guard.state().stoodDown);
 guard.reset();assert(!guard.state().stoodDown&&!guard.state().escalated,'next exit re-arms the guard');guard.onPlay({target:video});assert.equal(pauses,5);}

// Reentrant play events raised from inside our own pause are ignored rather than recursed into.
{let depth=0,max=0;const guard=X.pauseGuard({isActive:()=>true,pause:v=>{depth++;max=Math.max(max,depth);guard.onPlay({target:v});depth--;}});guard.onPlay({target:{tagName:'VIDEO'}});assert.equal(max,1);}

// Spaced-out late plays (outside the window) are each paused and never escalate; inactive/non-video ignored.
{let t=0,pauses=0,stops=0;const guard=X.pauseGuard({isActive:()=>true,now:()=>t,pause:()=>pauses++,stop:()=>stops++});
 for(let i=0;i<50;i++){t+=3000;guard.onPlay({target:{tagName:'VIDEO'}});}assert.equal(pauses,50);assert.equal(stops,0);
 let active=false;const idle=X.pauseGuard({isActive:()=>active,pause:()=>{throw Error('must not pause during playback');}});idle.onPlay({target:{tagName:'VIDEO'}});
 active=true;idle.onPlay({target:{tagName:'DIV'}});idle.onPlay({});}

// Source contracts: one idempotent exit, no unbounded pause listener, observer idle during playback,
// Back debounced after exit, and the bundle includes the helper ahead of app.js.
const app=fs.readFileSync(__dirname+'/src/app.js','utf8');
assert(/function exitPlayback\(\)\{\s*if\(!playbackActive\)return false;/.test(app),'exit is idempotent');
assert.equal((app.match(/playbackActive=false/g)||[]).length,2,'only the declaration and exitPlayback clear playbackActive');
assert(app.includes('FTV_PLAYBACK_EXIT.run(['),'teardown steps are isolated');
assert(!/addEventListener\('play',function/.test(app),'no unbounded inline play listener');
assert(app.includes('if(playbackActive||changes.every('),'source observer ignores playback churn');
assert(/Date\.now\(\)-playbackExitAt>=BACK_SETTLE_MS/.test(app),'Back settles after playback exit');
const {modules}=require('./bundle.cjs');assert(modules.includes('src/playback-exit.js'),'helper is bundled');
console.log('PASS: isolated teardown, player-API pause with element fallback, bounded guard with single stop, reentrancy, re-arm, late plays and exit contracts.');
