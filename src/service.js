/* TizenBrew service bridge. ES5 / Node 4 compatible; Node built-ins only.
 * Only fixed recommendation and public-catalogue endpoints are relayed; Gorse is never exposed to the LAN.
 */
(function () {
  'use strict';
  var http = require('http');
  var relayHost = process.env.FTV_RELAY_HOST || '192.168.1.84';
  var localPort=Number(process.env.FTV_PORT)||8770;
  var allowedOrigins = ['http://127.0.0.1:'+localPort, 'http://127.0.0.1:8765', 'http://localhost:8765'];
  var server = http.createServer(function (req, res) {
    if(req.method==='GET'&&req.url==='/tv'){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'origin','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src https://img.xcdn.to https://image.tmdb.org data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"});res.end(FTV_SHELL);return;}
    var origin = req.headers.origin;
    if (origin && allowedOrigins.indexOf(origin) < 0) { res.writeHead(403); res.end(); return; }
    if (origin) res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Private-Network', 'true');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Cache-Control', 'no-store');
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
