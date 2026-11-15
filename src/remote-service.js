/* Remote recommendation connection, ES5 / Node 4; Node built-ins only.
 * One private file (<cache>/remote.json, mode 600) records a paired remote endpoint and its device
 * token. target() is the single precedence rule: a paired remote wins over the LAN relay, with no
 * silent fallback. HTTPS trusts only the pinned roots in FTV_REMOTE_TRUST (not the TV's store) and
 * keeps hostname verification on. The token never leaves this service except to the paired server.
 */
var FTV_REMOTE=(function(){
  var fs=require('fs'),path=require('path'),http=require('http'),https=require('https');
  var PASS=[200,202,400,401,403,404,413,415,429];
  function create(options){
    var trust=options.trust,file=path.join(options.directory,'remote.json'),lan=options.lan;
    // Node 4 has no WHATWG URL; accept only https://host[:port] with no path, user or query.
    var m=/^https:\/\/([a-z0-9.-]+)(?::(\d{1,5}))?$/.exec(trust.url||'');
    if(!m)throw Error('Remote endpoint must be https://host[:port]');
    var endpoint={hostname:m[1],port:m[2]?Number(m[2]):443};
    var lastError='',lastSource='';
    function read(){
      try{var v=JSON.parse(fs.readFileSync(file,'utf8'));
        if(v.schema!==1||v.url!==trust.url||typeof v.token!=='string'||v.token.length<20||typeof v.label!=='string'||!Array.isArray(v.profiles))return null;
        return v;}catch(_){return null;}
    }
    function write(value){
      if(!fs.existsSync(options.directory))fs.mkdirSync(options.directory,448);
      fs.writeFileSync(file+'.tmp',JSON.stringify(value),{mode:384});fs.chmodSync(file+'.tmp',384);fs.renameSync(file+'.tmp',file);
    }
    function forget(){try{fs.unlinkSync(file);}catch(_){}lastError='';}
    // Single precedence: paired remote > LAN relay. Returns {source, ...request target}.
    function target(){
      var paired=read();
      if(paired)return {source:'remote',paired:paired};
      return {source:'lan'};
    }
    function connection(){
      var paired=read();
      return {mode:paired?'remote':'lan',paired:!!paired,label:paired?paired.label:'',profiles:paired?paired.profiles:[],lastSource:lastSource,error:lastError};
    }
    // Low-level request. done(code, bodyText, source). Codes outside PASS become 503.
    function send(t,route,method,body,done){
      var finished=false;
      function finish(code,text){if(finished)return;finished=true;lastSource=t.source;
        if(t.source==='remote')lastError=code===200||code===202?'':code===401||code===403?'remote-'+code:code>=500?'unreachable':lastError;
        done(PASS.indexOf(code)>=0?code:503,text,t.source);}
      var headers={'User-Agent':'FlixTor-TV/remote-1'};
      if(method==='POST'){headers['Content-Type']='application/json';headers['Content-Length']=Buffer.byteLength(body);}
      var req;
      function receive(res){var text='';
        res.on('data',function(part){text+=part;if(text.length>150000){req.abort();finish(502,'{"error":"Response too large"}');}});
        res.on('end',function(){finish(res.statusCode,text);});
        res.on('error',function(){finish(503,'{"error":"Connection interrupted"}');});}
      if(t.source==='remote'){
        if(t.paired.token)headers.Authorization='Bearer '+t.paired.token;
        req=https.request({hostname:endpoint.hostname,port:endpoint.port,path:route,method:method,headers:headers,
          ca:trust.cas,servername:endpoint.hostname,rejectUnauthorized:true,agent:false},receive);
      }else{
        req=http.request({hostname:lan.host,port:lan.port,path:route,method:method,headers:headers},receive);
      }
      req.setTimeout(t.source==='remote'?15000:10000,function(){req.abort();finish(503,t.source==='remote'?'{"error":"Recommendation server did not respond","code":"unreachable"}':'{"error":"Mac recommendation server did not respond"}');});
      req.on('error',function(){finish(503,t.source==='remote'?'{"error":"Cannot reach the recommendation server","code":"unreachable"}':'{"error":"Start the recommendation relay on the Mac"}');});
      req.end(body||'');
    }
    function forward(route,method,body,done){send(target(),route,method,body,done);}
    // Pair: exchange the code over pinned HTTPS; store the token only on success.
    function pair(code,done){
      if(typeof code!=='string'||!/^[A-Za-z0-9 -]{8,12}$/.test(code)){done(400,{error:'Enter the 8-character code.'});return;}
      send({source:'remote',paired:{token:''}},'/pair','POST',JSON.stringify({code:code}),function(status,text){
        var value;try{value=JSON.parse(text);}catch(_){value={};}
        if(status!==200){done(status===401||status===429||status===400?status:503,{error:value.error||'Cannot reach the recommendation server',code:value.code||'unreachable'});return;}
        if(typeof value.token!=='string'||value.token.length<20||typeof value.label!=='string'||!Array.isArray(value.profiles)){done(502,{error:'Unexpected pairing response'});return;}
        var profiles=value.profiles.filter(function(p){return p&&typeof p.id==='string'&&typeof p.name==='string';}).slice(0,20).map(function(p){return {id:p.id,name:p.name.slice(0,100)};});
        try{write({schema:1,url:trust.url,token:value.token,label:value.label.slice(0,40),profiles:profiles,pairedAt:new Date().toISOString()});}
        catch(_){done(500,{error:'Could not save the connection on this TV'});return;}
        lastError='';done(200,connection());
      });
    }
    return {target:target,connection:connection,forward:forward,pair:pair,forget:forget};
  }
  return {create:create};
}());
if(typeof module!=='undefined'&&module.exports)module.exports=FTV_REMOTE;
