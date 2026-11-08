const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const manager=require('./src/updater-service.js');
const pair=crypto.generateKeyPairSync('rsa',{modulusLength:2048});
const pem=pair.publicKey.export({type:'spki',format:'pem'}),jwk=pair.publicKey.export({format:'jwk'});
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'ftv-updater-'));
function release(version,bridge=1){const payload=JSON.stringify({schema:1,bridge,version,code:'/* '+version+' */ window.exampleRuntime='+JSON.stringify(version)+';'+(' '.repeat(120))});const manifest={schema:1,bridge,version,path:'updates/releases/'+version+'.json',sha256:crypto.createHash('sha256').update(payload).digest('hex')};manifest.signature=crypto.sign('RSA-SHA256',Buffer.from(manager.canonical(manifest)),pair.privateKey).toString('base64');return {manifest,payload};}
const base=release('1.0.0'),next=release('1.1.0');let offered=next,offline=false,requests=[];
function download(url,max,done){requests.push(url);if(offline)return done(Error('offline'));done(null,url.includes('stable.json')?JSON.stringify(offered.manifest):offered.payload);}
function instance(name='cache'){return manager.create({baseline:base,publicKey:pem,directory:path.join(temp,name),download});}
function check(m){return new Promise(resolve=>m.check(resolve));}
async function launcher(envelope,{badSignature=false,cached=false}={}){
  const scripts=[],store=new Map(),history=[];const value=JSON.parse(JSON.stringify(envelope));if(badSignature)value.manifest.signature='AAAA';
  const win={crypto:crypto.webcrypto};win.top=win.self=win;
  const location={hostname:'flixtor.to',pathname:cached?'/watch/movie/1/example':'/home',search:'',hash:cached?'':'#ftv-runtime='+encodeURIComponent(JSON.stringify({envelope:value,hash:'#ftv-details'})),href:'https://flixtor.to/home',replace:url=>scripts.push({redirect:url})};
  if(cached)store.set('ftv.signed-runtime.v1',JSON.stringify(value));
  const context={window:win,location,history:{replaceState:(...args)=>history.push(args)},document:{head:{appendChild:s=>{if(s.kind==='script')scripts.push(s.textContent);}},createElement:kind=>({kind,remove(){}})},localStorage:{setItem:(k,v)=>store.set(k,v),getItem:k=>store.get(k)},FTV_BASELINE:base,FTV_PUBLIC_JWK:jwk,FTV_LAUNCH_ORIGIN:'http://127.0.0.1:8770',Uint8Array,atob:s=>Buffer.from(s,'base64').toString('binary'),encodeURIComponent,decodeURIComponent,unescape};
  vm.createContext(context);vm.runInContext(fs.readFileSync('src/launcher.js','utf8'),context);
  for(let i=0;i<100&&!scripts.length;i++)await new Promise(resolve=>setTimeout(resolve,5));
  return {scripts,store,history};
}
(async()=>{
  try{
    const m=instance();await check(m);assert.equal(m.status().current,'1.0.0','download must not switch a running app');assert.equal(m.status().pending,'1.1.0');
    m.select();assert.equal(m.status().current,'1.1.0');m.healthy('1.1.0');m.select();m.select();assert.equal(m.status().current,'1.1.0');
    assert.equal(instance().status().current,'1.1.0','cache survives a service restart');
    offline=true;await check(m);assert.equal(m.status().current,'1.1.0');offline=false;
    assert(m.rollback());assert.equal(m.status().current,'1.0.0');await check(m);assert.equal(m.status().pending,null,'manually rejected version must not reinstall itself');
    const trial=instance('trial');await check(trial);trial.select();trial.select();trial.select();assert.equal(trial.status().current,'1.0.0','unhealthy startup automatically restores previous');
    const bad=instance('bad');offered={manifest:{...next.manifest,path:'https://attacker.invalid/code'},payload:next.payload};requests=[];await check(bad);assert.equal(requests.length,1);assert.equal(bad.status().pending,null);
    offered={manifest:next.manifest,payload:next.payload+'tampered'};await check(bad);assert.equal(bad.status().pending,null);
    offered=release('2.0.0',2);await check(bad);assert.equal(bad.status().pending,null,'new bridge protocol requires manual migration');
    offered=next;fs.writeFileSync(path.join(temp,'cache/state.json'),'{broken');assert.equal(instance().status().current,'1.0.0');
    const valid=await launcher(next);assert.equal(valid.scripts[0],JSON.parse(next.payload).code);assert(valid.store.has('ftv.signed-runtime.v1'));assert(valid.history[0][2].endsWith('#ftv-details'));
    const invalid=await launcher(next,{badSignature:true});assert.equal(invalid.scripts[0],JSON.parse(base.payload).code,'unverified fragment must never execute');
    const cache=await launcher(next,{cached:true});assert.equal(cache.scripts[0],JSON.parse(next.payload).code);
    console.log('PASS: signed update staging/activation, persistent offline cache, rollback/quarantine, failed boot recovery, URL/signature/hash/protocol rejection, browser verification and native-page cache.');
  }finally{fs.rmSync(temp,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
