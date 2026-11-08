/* Stable TizenBrew launcher. Inline scripts are permitted by FlixTor's CSP;
 * no eval, policy changes, remote script tags, or session-cookie transfers. */
(function(){
  if(window.top!==window.self||window.FTV_LAUNCHING)return;
  if(location.hostname!=='flixtor.to')return;
  window.FTV_LAUNCHING=true;
  var origin=FTV_LAUNCH_ORIGIN,key='ftv.signed-runtime.v1';
  var cover=null;
  if(!/^#ftv-(original|search)$/.test(location.hash)&&!/^\/(vipsignin|account|faq|dmca)/.test(location.pathname)){cover=document.createElement('style');cover.textContent='html{background:#090d12!important}body{visibility:hidden!important}';(document.head||document.documentElement).appendChild(cover);}
  function execute(code){window.FTV_BRIDGE_ORIGIN=origin;var script=document.createElement('script');script.textContent=code;(document.head||document.documentElement).appendChild(script);script.remove();if(cover)cover.remove();}
  function fallback(){execute(JSON.parse(FTV_BASELINE.payload).code);}
  function bytes(text){var s=atob(text),out=new Uint8Array(s.length);for(var i=0;i<s.length;i++)out[i]=s.charCodeAt(i);return out;}
  function utf8(text){var s=unescape(encodeURIComponent(text)),out=new Uint8Array(s.length);for(var i=0;i<s.length;i++)out[i]=s.charCodeAt(i);return out;}
  function verified(envelope){
    var m=envelope&&envelope.manifest;
    if(!m||m.schema!==1||m.bridge!==1||! /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(m.version)||m.path!=='updates/releases/'+m.version+'.json'||! /^[a-f0-9]{64}$/.test(m.sha256)||typeof envelope.payload!=='string'||envelope.payload.length>1000000)throw Error();
    var subtle=window.crypto&&window.crypto.subtle;if(!subtle)throw Error();
    return subtle.importKey('jwk',FTV_PUBLIC_JWK,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']).then(function(publicKey){return subtle.verify({name:'RSASSA-PKCS1-v1_5'},publicKey,bytes(m.signature),utf8([m.schema,m.bridge,m.version,m.path,m.sha256].join('\n')));}).then(function(ok){if(!ok)throw Error();return subtle.digest('SHA-256',utf8(envelope.payload));}).then(function(digest){var hash=Array.prototype.map.call(new Uint8Array(digest),function(v){return ('0'+v.toString(16)).slice(-2);}).join('');if(hash!==m.sha256)throw Error();var payload=JSON.parse(envelope.payload);if(payload.schema!==1||payload.bridge!==1||payload.version!==m.version||typeof payload.code!=='string')throw Error();return payload.code;});
  }
  function use(envelope){try{verified(envelope).then(function(code){try{localStorage.setItem(key,JSON.stringify(envelope));}catch(_){}execute(code);},fallback);}catch(_){fallback();}}
  var incoming=null;
  if(location.hash.indexOf('#ftv-runtime=')===0){try{incoming=JSON.parse(decodeURIComponent(location.hash.slice(13)));history.replaceState(null,'',location.pathname+location.search+(typeof incoming.hash==='string'&&/^#ftv-(?:details|play|return|original)$/.test(incoming.hash)?incoming.hash:''));}catch(_){fallback();return;}use(incoming.envelope);return;}
  var original=/^#ftv-(original|search|collect=)/.test(location.hash),home=location.pathname==='/home'||location.pathname==='/';
  var cached=null;try{cached=JSON.parse(localStorage.getItem(key)||'null');}catch(_){}
  if(home&&!original){location.replace(origin+'/launch#'+encodeURIComponent(JSON.stringify({target:location.href})));return;}
  if(cached){use(cached);return;}
  if(/^\/watch\//.test(location.pathname)&&!original){location.replace(origin+'/launch#'+encodeURIComponent(JSON.stringify({target:location.href})));return;}
  fallback();
}());
