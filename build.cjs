const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=__dirname;
const version=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).version;
const bundle=require('./bundle.cjs').appBundle(root);
fs.writeFileSync(path.join(root,'tv.js'),bundle);
// The private signing key lives outside the repository and never ships to a TV.
const keyDir=path.resolve(root,'../private-updater'),keyFile=path.join(keyDir,'signing-key.pem'),publicFile=path.join(root,'updater-public-key.json');
if(!fs.existsSync(keyFile)){
  if(fs.existsSync(publicFile))throw Error('Restore the existing private updater signing key before publishing.');
  fs.mkdirSync(keyDir,{recursive:true,mode:0o700});
  fs.writeFileSync(keyFile,crypto.generateKeyPairSync('rsa',{modulusLength:2048,privateKeyEncoding:{type:'pkcs8',format:'pem'},publicKeyEncoding:{type:'spki',format:'pem'}}).privateKey,{mode:0o600});
}
const privateKey=crypto.createPrivateKey(fs.readFileSync(keyFile)),publicKey=crypto.createPublicKey(privateKey);
const trust={pem:publicKey.export({type:'spki',format:'pem'}),jwk:publicKey.export({format:'jwk'})};
if(fs.existsSync(publicFile)&&JSON.parse(fs.readFileSync(publicFile)).pem!==trust.pem)throw Error('Updater signing key does not match pinned public key.');
fs.writeFileSync(publicFile,JSON.stringify(trust,null,2)+'\n');
const payload=JSON.stringify({schema:1,bridge:1,version,code:bundle});
const manifest={schema:1,bridge:1,version,path:'updates/releases/'+version+'.json',sha256:crypto.createHash('sha256').update(payload).digest('hex')};
manifest.signature=crypto.sign('RSA-SHA256',Buffer.from([manifest.schema,manifest.bridge,manifest.version,manifest.path,manifest.sha256].join('\n')),privateKey).toString('base64');
const envelope={manifest,payload};
fs.mkdirSync(path.join(root,'updates/releases'),{recursive:true});
fs.writeFileSync(path.join(root,manifest.path),payload);
fs.writeFileSync(path.join(root,'updates/stable.json'),JSON.stringify(manifest,null,2)+'\n');
const launcherCode=fs.readFileSync(path.join(root,'src/launcher.js'),'utf8');
function launcher(origin){return '/* FlixTor TV stable launcher 1 */\nvar FTV_LAUNCH_ORIGIN='+JSON.stringify(origin)+';\nvar FTV_BASELINE='+JSON.stringify(envelope)+';\nvar FTV_PUBLIC_JWK='+JSON.stringify(trust.jwk)+';\n'+launcherCode;}
fs.writeFileSync(path.join(root,'tv-'+version+'.js'),launcher('http://127.0.0.1:8773'));
const sample=fs.readFileSync(path.join(root,'preview/sample.js'),'utf8');
fs.writeFileSync(path.join(root,'FlixTor_TV_Preview.html'),'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FlixTor TV</title></head><body><script>'+sample+'</script><script>'+bundle+'</script></body></html>');
console.log('Built tv.js and FlixTor_TV_Preview.html');

const shell='<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FlixTor TV</title></head><body><script>'+bundle.replace(/<\/script/gi,'<\\/script')+'</script></body></html>';
fs.writeFileSync(path.join(root,'FlixTor_TV_Live.html'),shell);
const {serviceCode,remoteTrust}=require('./bundle.cjs');
fs.writeFileSync(path.join(root,'service.js'),'/* Generated TizenBrew service; stable updater protocol 1 */\nvar FTV_SHELL='+JSON.stringify(shell)+';\nvar FTV_BASELINE='+JSON.stringify(envelope)+';\nvar FTV_UPDATE_PUBLIC_KEY='+JSON.stringify(trust.pem)+';\nvar FTV_REMOTE_TRUST='+JSON.stringify(remoteTrust(root))+';\n'+serviceCode(root));

// The browser helper reapplies the same module after native FlixTor navigations.
// No background worker, browsing-history permission, or access to other sites.
const chromeDir=path.join(root,'chrome');
fs.mkdirSync(chromeDir,{recursive:true});
fs.writeFileSync(path.join(chromeDir,'tv.js'),launcher('http://127.0.0.1:8771'));
fs.writeFileSync(path.join(chromeDir,'manifest.json'),JSON.stringify({
  manifest_version:3,
  name:'FlixTor TV — Live Browser Test',
  version:JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).version,
  description:'Test the full TV interface using your existing FlixTor session and local recommendation service.',
  content_scripts:[{
    matches:['https://flixtor.to/*'],
    js:['tv.js'],
    run_at:'document_start',
    world:'MAIN',
    all_frames:false
  }]
},null,2)+'\n');
