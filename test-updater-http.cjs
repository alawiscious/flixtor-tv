// Exercise the actual service routes on an isolated port/cache with signed test releases.
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http'),{spawn}=require('node:child_process');
const manager=require('./src/updater-service.js'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'ftv-update-http-')),port=30000+process.pid%20000;
const keys=crypto.generateKeyPairSync('rsa',{modulusLength:2048}),pem=keys.publicKey.export({type:'spki',format:'pem'});
function envelope(version){const payload=JSON.stringify({schema:1,bridge:1,version,code:fs.readFileSync('tv.js','utf8').replace(/var FTV_VERSION="[^"]+";/,'var FTV_VERSION="'+version+'";')});const manifest={schema:1,bridge:1,version,path:'updates/releases/'+version+'.json',sha256:crypto.createHash('sha256').update(payload).digest('hex')};manifest.signature=crypto.sign('RSA-SHA256',Buffer.from(manager.canonical(manifest)),keys.privateKey).toString('base64');return {manifest,payload};}
const base=envelope('0.3.6'),next=envelope('0.3.7');fs.writeFileSync(path.join(dir,'offered.json'),JSON.stringify(next));
const code='var FTV_BASELINE='+JSON.stringify(base)+';var FTV_UPDATE_PUBLIC_KEY='+JSON.stringify(pem)+';var FTV_SHELL="";var original=require("./src/updater-service.js");var FTV_UPDATE_MANAGER={create:function(options){options.download=function(url,max,done){try{var v=JSON.parse(require("fs").readFileSync('+JSON.stringify(path.join(dir,'offered.json'))+',"utf8"));done(null,url.indexOf("stable.json")>=0?JSON.stringify(v.manifest):v.payload);}catch(e){done(Error("offline"));}};return original.create(options);}};'+fs.readFileSync('src/service.js','utf8');
let child;
function start(){child=spawn(process.execPath,['-e',code],{cwd:__dirname,env:{...process.env,FTV_PORT:String(port),FTV_UPDATE_CACHE:path.join(dir,'cache'),FTV_UPDATES_OFF:'1'},stdio:['ignore','ignore','pipe']});child.stderr.on('data',b=>process.stderr.write(b));}
function request(route,body,token,origin='http://127.0.0.1:'+port){return new Promise((resolve,reject)=>{const text=body===undefined?null:JSON.stringify(body);const r=http.request({host:'127.0.0.1',port,path:route,method:text===null?'GET':'POST',headers:text===null?{}:{Origin:origin,'Content-Type':'application/json','X-FTV-Update-Token':token||'','Content-Length':Buffer.byteLength(text)}},res=>{let data='';res.on('data',b=>data+=b);res.on('end',()=>resolve({code:res.statusCode,body:data,headers:res.headers}));});r.on('error',reject);r.end(text);});}
async function ready(){for(let i=0;i<50;i++){try{return await request('/updates/status');}catch(_){await new Promise(r=>setTimeout(r,30));}}throw Error('Test service did not start');}
async function stop(){if(child){await new Promise(resolve=>{child.once('exit',resolve);child.kill();});child=null;}}
(async()=>{try{
  start();await ready();let page=await request('/tv');let token=page.body.match(/window.FTV_UPDATE_TOKEN="([a-f0-9]+)"/)[1];
  assert(page.body.includes('FTV_VERSION="0.3.6"'));assert(page.headers['content-security-policy'].includes("connect-src 'self'"));
  assert.equal((await request('/updates/check',{},token,'https://untrusted.invalid')).code,403);
  assert.equal((await request('/updates/check',{},'incorrect')).code,403);
  const checked=JSON.parse((await request('/updates/check',{},token)).body);assert.equal(checked.current,'0.3.6');assert.equal(checked.pending,'0.3.7');
  page=await request('/tv');assert(page.body.includes('FTV_VERSION="0.3.7"'));assert.equal(JSON.parse((await request('/updates/status')).body).trial,true);
  assert.equal(JSON.parse((await request('/updates/healthy',{version:'0.3.7'},token)).body).healthy,true);
  await stop();fs.renameSync(path.join(dir,'offered.json'),path.join(dir,'offline.json'));start();await ready();
  page=await request('/tv');assert(page.body.includes('FTV_VERSION="0.3.7"'),'real service restart retains latest payload while offline');token=page.body.match(/window.FTV_UPDATE_TOKEN="([a-f0-9]+)"/)[1];
  assert.equal(JSON.parse((await request('/updates/rollback',{},token)).body).rolledBack,true);
  assert((await request('/tv')).body.includes('FTV_VERSION="0.3.6"'));
  console.log('PASS: actual HTTP service update staging, activation, health acknowledgment, restart/offline recovery, rollback and cross-origin/token rejection.');
}finally{await stop();fs.rmSync(dir,{recursive:true,force:true});}})().catch(e=>{console.error(e);process.exitCode=1;});
