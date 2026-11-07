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
