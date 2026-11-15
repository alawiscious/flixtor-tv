// TV service remote connection: pairing over pinned HTTPS, precedence (paired remote > LAN, no silent
// fallback), token storage, wrong-CA and wrong-hostname rejection. Real service process, local test CA.
// Does not prove the Samsung Node/OpenSSL runtime; that needs a physical TV.
'use strict';
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),
  http=require('node:http'),https=require('node:https'),{spawn,execFileSync}=require('node:child_process');
const manager=require('./src/updater-service.js');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ftv-remote-'));
const openssl=['/usr/bin/openssl','/opt/homebrew/bin/openssl'].find(p=>fs.existsSync(p))||'openssl';
const ssl=(...a)=>execFileSync(openssl,a,{cwd:dir,stdio:['ignore','ignore','pipe']});
fs.writeFileSync(path.join(dir,'ca.cnf'),'[req]\ndistinguished_name=dn\n[dn]\n[v3_ca]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n');
function ca(name){ssl('req','-x509','-sha384','-newkey','ec','-pkeyopt','ec_paramgen_curve:secp384r1','-pkeyopt','ec_param_enc:named_curve','-nodes','-keyout',name+'.key','-out',name+'.pem','-subj','/CN='+name,'-days','2','-config','ca.cnf','-extensions','v3_ca');return fs.readFileSync(path.join(dir,name+'.pem'),'utf8');}
function leaf(name,host,issuer){
  ssl('req','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1','-pkeyopt','ec_param_enc:named_curve','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN='+host,'-config','ca.cnf');
  fs.writeFileSync(path.join(dir,name+'.ext'),'subjectAltName=DNS:'+host+'\nbasicConstraints=CA:FALSE\n');
  ssl('x509','-req','-sha256','-in',name+'.csr','-CA',issuer+'.pem','-CAkey',issuer+'.key','-CAcreateserial','-out',name+'.pem','-days','2','-extfile',name+'.ext');
  return {key:fs.readFileSync(path.join(dir,name+'.key')),cert:fs.readFileSync(path.join(dir,name+'.pem'))};
}
const caA=ca('caA');ca('caB');
const good=leaf('good','localhost','caA'),wrongCA=leaf('wrongca','localhost','caB'),wrongHost=leaf('wronghost','other.test','caA');

// Fake paired-device server (mirrors backend/relay.py public_handler responses).
const TOKEN='tok_'+'x'.repeat(40);let revoked=false;
function remoteServer(tls){const seen=[];const s=https.createServer(tls,(req,res)=>{let body='';req.on('data',b=>body+=b);req.on('end',()=>{
  seen.push({url:req.url,method:req.method,auth:req.headers.authorization||'',body});
  const reply=(c,v)=>{res.writeHead(c,{'Content-Type':'application/json'});res.end(JSON.stringify(v));};
  if(req.url==='/pair'){const code=JSON.parse(body).code;return code==='GOOD-CODE'?reply(200,{token:TOKEN,label:'Remote TV',profiles:[{id:'ftv-netflix-'+'a'.repeat(16),name:'Viewer One'}]}):reply(401,{error:'Pairing code is wrong or expired',code:'bad-code'});}
  if(req.headers.authorization!=='Bearer '+TOKEN)return reply(401,{error:'Pair this TV to use recommendations.',code:'unpaired'});
  if(revoked)return reply(403,{error:'Connection removed. Pair this TV again.',code:'revoked'});
  if(req.url==='/recommendations')return reply(200,{engine:'gorse',id:'ftv-netflix-'+'a'.repeat(16),items:[],profiles:[]});
  if(req.url==='/feedback')return reply(200,{saved:true,echo:JSON.parse(body)});
  reply(404,{error:'Not found'});});});return {server:s,seen};}
const lanSeen=[];const lan=http.createServer((req,res)=>{lanSeen.push(req.url);res.writeHead(200,{'Content-Type':'application/json'});res.end('{"lan":true}');});
// No host: dual-stack, so 'localhost' works whether it resolves to ::1 or 127.0.0.1.
const listen=s=>new Promise(r=>s.listen(0,()=>r(s.address().port)));

// Signed baseline so the real updater accepts the service start.
const keys=crypto.generateKeyPairSync('rsa',{modulusLength:2048}),pem=keys.publicKey.export({type:'spki',format:'pem'});
const payload=JSON.stringify({schema:1,bridge:1,version:'0.3.6',code:fs.readFileSync(path.join(__dirname,'tv.js'),'utf8')});
const manifest={schema:1,bridge:1,version:'0.3.6',path:'updates/releases/0.3.6.json',sha256:crypto.createHash('sha256').update(payload).digest('hex')};
manifest.signature=crypto.sign('RSA-SHA256',Buffer.from(manager.canonical(manifest)),keys.privateKey).toString('base64');
const {serviceCode}=require('./bundle.cjs');
let nextPort=31000+process.pid%15000;
function startService(trust,cache,lanPort){
  const port=nextPort++;
  const code='var FTV_SHELL="";var FTV_BASELINE='+JSON.stringify({manifest,payload})+';var FTV_UPDATE_PUBLIC_KEY='+JSON.stringify(pem)+';var FTV_REMOTE_TRUST='+JSON.stringify(trust)+';\n'+serviceCode(__dirname);
  const child=spawn(process.execPath,['-e',code],{env:{...process.env,FTV_PORT:String(port),FTV_UPDATE_CACHE:cache,FTV_UPDATES_OFF:'1',FTV_RELAY_HOST:'127.0.0.1',FTV_RELAY_PORT:String(lanPort)},stdio:['ignore','ignore','pipe']});
  let err='';child.stderr.on('data',b=>err+=b);
  const origin='http://127.0.0.1:'+port;
  const call=(route,body,{token='',from=origin}={})=>new Promise((resolve,reject)=>{const text=body===undefined?null:JSON.stringify(body);
    const r=http.request({host:'127.0.0.1',port,path:route,method:text===null?'GET':'POST',headers:text===null?{}:{Origin:from,'Content-Type':'application/json','X-FTV-Update-Token':token,'Content-Length':Buffer.byteLength(text)}},res=>{let d='';res.on('data',b=>d+=b);res.on('end',()=>resolve({code:res.statusCode,body:d,json:(()=>{try{return JSON.parse(d);}catch(_){return null;}})(),source:res.headers['x-ftv-source']}));});r.on('error',reject);r.end(text);});
  return {call,origin,err:()=>err,async ready(){for(let i=0;i<80;i++){try{await call('/connection');const page=await call('/tv');return page.body.match(/window.FTV_UPDATE_TOKEN="([a-f0-9]+)"/)[1];}catch(_){await new Promise(r=>setTimeout(r,30));}}throw Error('service did not start: '+err);},
    stop(){return new Promise(r=>{child.once('exit',r);child.kill();});}};
}

(async()=>{const services=[];try{
  const lanPort=await listen(lan);
  const A=remoteServer(good),B=remoteServer(wrongCA),C=remoteServer(wrongHost);
  const [pa,pb,pc]=[await listen(A.server),await listen(B.server),await listen(C.server)];
  const trust={url:'https://localhost:'+pa,cas:[caA]},cache=path.join(dir,'cache');

  let svc=startService(trust,cache,lanPort);services.push(svc);let token=await svc.ready();
  // Unpaired: LAN relay, remote untouched.
  assert.deepEqual((await svc.call('/connection')).json,{mode:'lan',paired:false,label:'',profiles:[],lastSource:'',error:''});
  let r=await svc.call('/recommendations');assert.equal(r.source,'lan');assert.equal(r.json.lan,true);assert.equal(A.seen.length,0);

  // State-changing endpoints need the bridge origin AND the shell token (origin shadowing fixed).
  assert.equal((await svc.call('/pair',{code:'GOOD-CODE'})).code,403,'no token');
  assert.equal((await svc.call('/pair',{code:'GOOD-CODE'},{token,from:'http://127.0.0.1:8765'})).code,403,'allowed CORS origin is not the bridge');
  assert.equal((await svc.call('/updates/check',{},{token,from:'http://127.0.0.1:8765'})).code,403,'update gate also checks the bridge origin');
  assert.equal(A.seen.length,0);

  // Pairing: wrong code passes through, nothing stored; right code stores the token privately.
  r=await svc.call('/pair',{code:'BAD-CODE1'},{token});assert.equal(r.code,401);assert.equal(r.json.code,'bad-code');assert.equal(A.seen[0].auth,'','no Authorization header while pairing');
  assert(!fs.existsSync(path.join(cache,'remote.json')));
  assert.equal((await svc.call('/pair',{code:'<script>'},{token})).code,400);
  r=await svc.call('/pair',{code:'GOOD-CODE'},{token});assert.equal(r.code,200,r.body);
  assert.deepEqual(r.json,{mode:'remote',paired:true,label:'Remote TV',profiles:[{id:'ftv-netflix-'+'a'.repeat(16),name:'Viewer One'}],lastSource:'remote',error:''});
  assert(!r.body.includes(TOKEN),'token never reaches the page');assert(!(await svc.call('/connection')).body.includes(TOKEN));
  const file=path.join(cache,'remote.json');assert.equal(fs.statSync(file).mode&0o777,0o600);assert.equal(JSON.parse(fs.readFileSync(file,'utf8')).token,TOKEN);

  // Paired: every relay route goes to the remote with the token; LAN is not consulted.
  const lanBefore=lanSeen.length;
  r=await svc.call('/recommendations');assert.equal(r.code,200);assert.equal(r.source,'remote');assert.equal(A.seen.at(-1).auth,'Bearer '+TOKEN);
  r=await svc.call('/feedback',{profileId:'ftv-netflix-'+'a'.repeat(16),itemId:'flixtor:movie:1',preference:'like'});assert.equal(r.code,200);assert.equal(r.json.echo.preference,'like');
  r=await svc.call('/plots');assert.equal(r.code,404);assert.equal(r.source,'remote');
  assert.equal(lanSeen.length,lanBefore,'no silent LAN fallback while paired');

  // Survives a service restart.
  await svc.stop();services.pop();svc=startService(trust,cache,lanPort);services.push(svc);token=await svc.ready();
  assert.equal((await svc.call('/connection')).json.paired,true);assert.equal((await svc.call('/recommendations')).source,'remote');

  // Revoked on the server: 403 passes through with its code; connection reports it.
  revoked=true;r=await svc.call('/recommendations');assert.equal(r.code,403);assert.equal(r.json.code,'revoked');
  assert.equal((await svc.call('/connection')).json.error,'remote-403');revoked=false;

  // Forget: back to the LAN relay, file removed.
  r=await svc.call('/connection/forget',{},{token});assert.equal(r.json.paired,false);assert(!fs.existsSync(file));
  assert.equal((await svc.call('/recommendations')).source,'lan');

  // A pairing file for a different endpoint is ignored (trust.url is part of the record).
  fs.writeFileSync(file,JSON.stringify({schema:1,url:'https://elsewhere.test',token:TOKEN,label:'x',profiles:[]}),{mode:0o600});
  assert.equal((await svc.call('/connection')).json.paired,false);fs.unlinkSync(file);
  await svc.stop();services.pop();

  // Wrong CA and wrong hostname: TLS fails before any HTTP request, so no code or token is sent.
  for(const [label,port,server] of [['wrong CA',pb,B],['wrong hostname',pc,C]]){
    const c=path.join(dir,'cache-'+port),t={url:'https://localhost:'+port,cas:[caA]};
    fs.mkdirSync(c,{mode:0o700});fs.writeFileSync(path.join(c,'remote.json'),JSON.stringify({schema:1,url:t.url,token:TOKEN,label:'x',profiles:[]}),{mode:0o600});
    const s=startService(t,c,lanPort);services.push(s);const tk=await s.ready();
    r=await s.call('/recommendations');assert.equal(r.code,503,label);assert.equal(r.json.code,'unreachable');assert.equal(r.source,'remote');
    fs.unlinkSync(path.join(c,'remote.json'));
    r=await s.call('/pair',{code:'GOOD-CODE'},{token:tk});assert.equal(r.code,503,label);assert(!fs.existsSync(path.join(c,'remote.json')));
    assert.equal(server.seen.length,0,label+': server received no HTTP request');
    await s.stop();services.pop();
  }

  // Service sources stay ES5 (a TV may run Node 4). Lexical check, not a parser.
  for(const f of ['src/remote-service.js','src/service.js','src/updater-service.js']){
    const src=fs.readFileSync(path.join(__dirname,f),'utf8').replace(/\/\*[\s\S]*?\*\//g,'').replace(/\/\/.*$/gm,'');
    for(const [name,re] of [['arrow function',/=>/],['let/const',/\b(let|const)\s/],['template literal',/`/],['class',/\bclass\s+[A-Z]/],['spread/rest',/\.\.\.[a-zA-Z]/],['async/await',/\b(async|await)\b/]])
      assert(!re.test(src),f+' uses '+name);
  }
  console.log('PASS: remote pairing over pinned HTTPS, token stored mode 600 and never shown to the page, paired remote > LAN with no silent fallback, revoke/forget/restart, bridge-origin gate, wrong CA/hostname rejected before any request, ES5 lexical check.');
}finally{for(const s of services)await s.stop();lan.close();fs.rmSync(dir,{recursive:true,force:true});}})().then(()=>process.exit(process.exitCode||0)).catch(e=>{console.error(e);process.exit(1);});
