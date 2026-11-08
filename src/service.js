/* TizenBrew service bridge. ES5 / Node 4 compatible; Node built-ins only.
 * Only fixed recommendation and public-catalogue endpoints are relayed; Gorse is never exposed to the LAN.
 */
(function () {
  'use strict';
  var http = require('http');
  var relayHost = process.env.FTV_RELAY_HOST || '192.168.1.84';
  var localPort=Number(process.env.FTV_PORT)||8773;
  var origin='http://127.0.0.1:'+localPort;
  var token=require('crypto').randomBytes(24).toString('hex');
  var fs=require('fs'),path=require('path'),home=require('os').homedir();
  var cacheDirectory=process.env.FTV_UPDATE_CACHE||path.join(fs.existsSync('/home/owner/share')?'/home/owner/share':home,'.flixtor-tv-updates');
  var updater=FTV_UPDATE_MANAGER.create({baseline:FTV_BASELINE,publicKey:FTV_UPDATE_PUBLIC_KEY,directory:cacheDirectory});
  function json(res,code,value){res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));}
  function literal(value){return JSON.stringify(value).replace(/</g,'\\u003c');}
  function shellFor(envelope){var payload=JSON.parse(envelope.payload);return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FlixTor TV</title></head><body><script>window.FTV_BRIDGE_ORIGIN='+literal(origin)+';window.FTV_UPDATE_TOKEN='+literal(token)+';<\/script><script>'+payload.code.replace(/<\/script/gi,'<\\/script')+'<\/script></body></html>';}
  function launchPage(){
    return '<!doctype html><html><head><meta charset="utf-8"><title>Opening FlixTor</title></head><body style="background:#090d12;color:white;font:28px Arial;padding:8vw"><p>Opening FlixTor…</p><script>('+function(envelope,token){
      var target;try{var data=JSON.parse(decodeURIComponent(location.hash.slice(1)));target=new URL(data.target);if(target.origin!=='https://flixtor.to'||!/^\/(?:home\/?$|watch\/(?:tv|movie)\/)/.test(target.pathname)||target.hash.indexOf('#ftv-runtime=')===0)throw Error();}catch(_){document.querySelector('p').textContent='Open FlixTor from TizenBrew to continue.';return;}
      var done=false;function go(value){if(done)return;done=true;var hash=target.hash;target.hash='ftv-runtime='+encodeURIComponent(JSON.stringify({envelope:value,hash:hash}));location.replace(target.href);}
      var req=new XMLHttpRequest();req.open('POST','/updates/check');req.setRequestHeader('Content-Type','application/json');req.setRequestHeader('X-FTV-Update-Token',token);req.timeout=8000;
      function ready(){var r=new XMLHttpRequest();r.open('GET','/updates/runtime');r.timeout=2000;r.onload=function(){try{if(r.status!==200)throw Error();go(JSON.parse(r.responseText));}catch(_){go(envelope);}};r.onerror=r.ontimeout=function(){go(envelope);};r.send();}
      req.onload=req.onerror=req.ontimeout=ready;req.send('{}');
    }.toString()+')('+literal(updater.current())+','+literal(token)+');<\/script></body></html>';
  }
  if(process.env.FTV_UPDATES_OFF!=='1'){setTimeout(function(){updater.check();},3000);setInterval(function(){updater.check();},300000);}
  var allowedOrigins = ['http://127.0.0.1:'+localPort, 'http://127.0.0.1:8765', 'http://localhost:8765'];
  var server = http.createServer(function (req, res) {
    if(req.method==='GET'&&(req.url==='/tv'||req.url==='/launch')){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src https://img.xcdn.to https://image.tmdb.org data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"});res.end(req.url==='/launch'?launchPage():shellFor(updater.select()));return;}
    var origin = req.headers.origin;
    if (origin && allowedOrigins.indexOf(origin) < 0) { res.writeHead(403); res.end(); return; }
    if (origin) res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Private-Network', 'true');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Cache-Control', 'no-store');
    if(req.method==='GET'&&req.url==='/updates/status'){json(res,200,updater.status());return;}
    if(req.method==='GET'&&req.url==='/updates/runtime'){json(res,200,updater.select());return;}
    if(req.method==='POST'&&/^\/updates\/(check|healthy|rollback)$/.test(req.url)){
      if(req.headers.origin!==origin||req.headers['x-ftv-update-token']!==token||req.headers['content-type']!=='application/json'){json(res,403,{error:'Update request denied'});return;}
      var updateBody='';req.on('data',function(chunk){updateBody+=chunk;if(updateBody.length>1000)req.destroy();});req.on('end',function(){
        var value;try{value=JSON.parse(updateBody);}catch(_){json(res,400,{error:'Invalid update request'});return;}
        if(req.url==='/updates/check')updater.check(function(status){json(res,200,status);});
        else if(req.url==='/updates/healthy')json(res,200,{healthy:updater.healthy(value.version)});
        else json(res,200,{rolledBack:updater.rollback(),status:updater.status()});
      });return;
    }
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
    var catalogue = req.method === 'POST' && req.url === '/catalogue';
    var feedback = req.method === 'POST' && req.url === '/feedback';
    var plots = req.url === '/plots' && (req.method === 'POST' || req.method === 'GET');
    if (!catalogue && !feedback && !plots && (req.method !== 'GET' || req.url !== '/recommendations')) { res.writeHead(404); res.end(); return; }
    var finished = false;
    function finish(code, value) {
      if (finished) return; finished = true;
      res.writeHead(code, {'Content-Type': 'application/json'}); res.end(value);
    }
    function forward(body) {
    var remote = http.request({hostname: relayHost, port: 8772, path: catalogue ? '/catalogue' : feedback ? '/feedback' : plots ? '/plots' : '/recommendations', method: req.method, headers: req.method === 'POST' ? {'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)} : {}}, function (upstream) {
      var body = '';
      upstream.on('data', function (part) { body += part; if (body.length > 150000) { remote.abort(); finish(502, '{"error":"Response too large"}'); } });
      upstream.on('end', function () { finish([200,202,400,413,415].indexOf(upstream.statusCode)>=0 ? upstream.statusCode : 503, body); });
      upstream.on('error', function () { finish(503, '{"error":"Connection interrupted"}'); });
    });
    remote.setTimeout(10000, function () { remote.abort(); finish(503, '{"error":"Mac recommendation server did not respond"}'); });
    remote.on('error', function () { finish(503, '{"error":"Start the recommendation relay on the Mac"}'); });
    remote.end(body);
    }
    if (req.method === 'POST') {
      var body = '';
      req.on('data', function (part) { body += part; if (Buffer.byteLength(body) > 100000) { finish(413, '{}'); req.destroy(); } });
      req.on('end', function () { if (!finished) forward(body); });
    } else forward('');
  });
  server.on('error', function (err) { if (err.code !== 'EADDRINUSE') console.error('FlixTor recommendation bridge: ' + err.code); });
  server.listen(localPort, '127.0.0.1');
}());
