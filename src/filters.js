var FTV_FILTERS=(function(){
  'use strict';
  function year(value){var n=Number(value);return Number.isInteger(n)&&n>=1900&&n<=2100?n:0;}
  function rating(value){var n=Number(value);return Number.isInteger(n)&&n>=1&&n<=9?n:0;}
  function read(href){var p=new URL(href,'https://flixtor.to').searchParams;return {from:year(p.get('yrf')),to:year(p.get('yrt')),rating:rating(p.get('rating'))};}
  function matches(item,state){var y=Number(item.year),r=Number(item.rating);return (!state.from||(y>0&&y>=state.from))&&(!state.to||(y>0&&y<=state.to))&&(!state.rating||(r>0&&r>=state.rating));}
  function target(href,key,value){
    var u=new URL(href,'https://flixtor.to');
    if(u.origin!=='https://flixtor.to')throw new Error('Invalid catalogue address.');
    if(key==='reset')u.search='';
    else {
      if(['yrf','yrt','rating'].indexOf(key)<0)throw new Error('Invalid filter.');
      var n=key==='rating'?rating(value):year(value);
      if(n)u.searchParams.set(key,String(n));else u.searchParams.delete(key);
      u.searchParams.delete('page');
      var state=read(u.href);
      if(state.from&&state.to&&state.from>state.to)throw new Error('The From year must be earlier than or equal to the To year.');
    }
    u.hash='';return u.href;
  }
  return {read:read,matches:matches,target:target};
}());
