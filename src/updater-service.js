/* Stable updater, ES5 / Node 4. Only signed browser payloads are downloaded.
 * This service never downloads or executes replacement Node/service code. */
var FTV_UPDATE_MANAGER=(function(){
  var fs=require('fs'),path=require('path'),crypto=require('crypto'),https=require('https');
  var feed='https://raw.githubusercontent.com/alawiscious/flixtor-tv/main/updates/stable.json';
  function canonical(m){return [m.schema,m.bridge,m.version,m.path,m.sha256].join('\n');}
  function newer(a,b){a=a.split('.').map(Number);b=b.split('.').map(Number);for(var i=0;i<3;i++){if(a[i]!==b[i])return a[i]>b[i];}return false;}
  function get(url,max,done){
    var ended=false,deadline;function finish(err,value){if(ended)return;ended=true;clearTimeout(deadline);done(err,value);}
    var requestOptions=require('url').parse(url);requestOptions.headers={'User-Agent':'FlixTor-TV-Updater/1','Cache-Control':'no-cache'};
    var req=https.get(requestOptions,function(res){
      if(res.statusCode!==200){res.resume();finish(Error('Update server unavailable'));return;}
      var chunks=[],length=0;res.on('data',function(b){length+=b.length;if(length>max){req.abort();finish(Error('Update too large'));}else chunks.push(b);});
      res.on('end',function(){finish(null,Buffer.concat(chunks).toString('utf8'));});res.on('error',function(){finish(Error('Download interrupted'));});
    });deadline=setTimeout(function(){req.abort();finish(Error('Update check timed out'));},3500);req.setTimeout(3500,function(){req.abort();finish(Error('Update check timed out'));});req.on('error',function(){finish(Error('Update server unavailable'));});
  }
  function create(options){
    var baseline=options.baseline,publicKey=options.publicKey,download=options.download||get;
    var state={current:baseline,previous:null,pending:null,blocked:[],trial:null},checking=false,waiters=[],lastError='',cacheFile=path.join(options.directory,'state.json');
    function verify(envelope){
      if(!envelope||typeof envelope.payload!=='string'||!envelope.manifest||Buffer.byteLength(envelope.payload)>1000000)throw Error('Invalid update');
      var m=envelope.manifest;
      if(m.schema!==1||m.bridge!==1||! /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(m.version)||m.path!=='updates/releases/'+m.version+'.json'||! /^[a-f0-9]{64}$/.test(m.sha256)||typeof m.signature!=='string')throw Error('Incompatible update');
      var checker=crypto.createVerify('RSA-SHA256');checker.update(canonical(m));
      if(!checker.verify(publicKey,m.signature,'base64')||crypto.createHash('sha256').update(envelope.payload).digest('hex')!==m.sha256)throw Error('Update verification failed');
      var p=JSON.parse(envelope.payload);
      if(p.schema!==1||p.bridge!==1||p.version!==m.version||typeof p.code!=='string'||p.code.length<100)throw Error('Invalid payload');
      return p;
    }
    function persist(){try{if(!fs.existsSync(options.directory))fs.mkdirSync(options.directory,448);fs.writeFileSync(cacheFile+'.tmp',JSON.stringify(state),{mode:384});fs.renameSync(cacheFile+'.tmp',cacheFile);}catch(_){lastError='TV cache could not be saved; bundled fallback remains available';}}
    verify(baseline);
    try{var saved=JSON.parse(fs.readFileSync(cacheFile,'utf8'));verify(saved.current);if(saved.previous)verify(saved.previous);if(saved.pending)verify(saved.pending);if(!Array.isArray(saved.blocked))throw Error();state=saved;}catch(_){}
    function status(){return {current:state.current.manifest.version,previous:state.previous&&state.previous.manifest.version,pending:state.pending&&state.pending.manifest.version,checking:checking,error:lastError,trial:!!state.trial,bridge:1};}
    function rollback(){
      if(!state.previous)return false;
      state.blocked.push(state.current.manifest.sha256);state.current=state.previous;state.previous=null;state.pending=null;state.trial=null;persist();return true;
    }
    function select(){
      if(state.trial){state.trial.attempts++;if(state.trial.attempts>2){rollback();lastError='Previous version restored after an unsuccessful start';}}
      if(state.pending&&!state.trial){state.previous=state.current;state.current=state.pending;state.pending=null;state.trial={attempts:1,version:state.current.manifest.version};}
      persist();return state.current;
    }
    function healthy(version){if(version===state.current.manifest.version){state.trial=null;persist();return true;}return false;}
    function check(done){
      waiters.push(done||function(){});if(checking)return;checking=true;lastError='';
      function finish(error){checking=false;if(error)lastError=error.message;var callbacks=waiters;waiters=[];callbacks.forEach(function(fn){fn(status());});}
      download(feed+'?check='+Date.now(),10000,function(err,text){
        if(err){finish(err);return;}
        var manifest;try{manifest=JSON.parse(text);verify({manifest:manifest,payload:baseline.payload});}catch(_){
          // Signature is checked before requesting a URL; payload hash is checked afterwards.
          try{manifest=JSON.parse(text);var m=manifest;if(m.schema!==1||m.bridge!==1||! /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(m.version)||m.path!=='updates/releases/'+m.version+'.json'||! /^[a-f0-9]{64}$/.test(m.sha256))throw Error();var v=crypto.createVerify('RSA-SHA256');v.update(canonical(m));if(!v.verify(publicKey,m.signature,'base64'))throw Error();}catch(_){finish(Error('Update manifest verification failed'));return;}
        }
        if(!newer(manifest.version,state.current.manifest.version)||state.blocked.indexOf(manifest.sha256)>=0){finish();return;}
        download('https://raw.githubusercontent.com/alawiscious/flixtor-tv/main/'+manifest.path,1000000,function(err,payload){
          if(err){finish(err);return;}
          try{var envelope={manifest:manifest,payload:payload};verify(envelope);state.pending=envelope;persist();finish();}catch(_){finish(Error('Update payload verification failed'));}
        });
      });
    }
    return {check:check,status:status,select:select,healthy:healthy,rollback:rollback,verify:verify,current:function(){return state.current;}};
  }
  return {create:create,canonical:canonical,newer:newer};
}());
if(typeof module!=='undefined'&&module.exports)module.exports=FTV_UPDATE_MANAGER;
