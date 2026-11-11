var FTV_FILTERS=(function(){
  'use strict';
  var nativeGenres=['Action','Adventure','Animation','Comedy','Crime','Documentary','Drama','Family','History','Horror','Music','Mystery','Romance','Sci-Fi & Fantasy','TV-Movie','Thriller','War','Western'];
  function resolveGenre(value){
    if(typeof value!=='string')return null;
    var text=value.trim().toLowerCase().replace(/\s+/g,' ');
    if(text===''||text==='all'||text==='all genres')return '';
    if(['science-fiction','science fiction','sci-fi','sci fi','fantasy'].indexOf(text)!==-1)return 'Sci-Fi & Fantasy';
    if(text==='tv movie')return 'TV-Movie';
    for(var i=0;i<nativeGenres.length;i++)if(nativeGenres[i].toLowerCase()===text)return nativeGenres[i];
    return null;
  }
  function canonicalGenre(value){return resolveGenre(value)||'';}
  function genres(){return ['All genres'].concat(nativeGenres);}
  function genreMatches(item,wanted){
    var metadata=String(item.meta||'').split(',');
    if(Array.isArray(item.genres))metadata=metadata.concat(item.genres);
    if(typeof item.genre==='string')metadata=metadata.concat(item.genre.split(','));
    return metadata.some(function(value){return resolveGenre(value)===wanted;});
  }
  function sort(value){return ['latest','best','name'].indexOf(value)!==-1?value:'';}
  function year(value){var n=Number(value);return Number.isInteger(n)&&n>=1900&&n<=2100?n:0;}
  function rating(value){var n=Number(value);return Number.isInteger(n)&&n>=1&&n<=9?n:0;}
  function read(href){var p=new URL(href,'https://flixtor.to').searchParams;return {from:year(p.get('yrf')),to:year(p.get('yrt')),rating:rating(p.get('rating')),genre:canonicalGenre(p.get('genre')),sort:sort(p.get('sort'))};}
  function matches(item,state){var y=Number(item.year),r=Number(item.rating);return (!state.genre||genreMatches(item,state.genre))&&(!state.from||(y>0&&y>=state.from))&&(!state.to||(y>0&&y<=state.to))&&(!state.rating||(r>0&&r>=state.rating));}
  function target(href,key,value){
    var u=new URL(href,'https://flixtor.to');
    if(u.origin!=='https://flixtor.to')throw new Error('Invalid catalogue address.');
    if(key==='reset')u.search='';
    else {
      if(['yrf','yrt','rating','genre','sort'].indexOf(key)<0)throw new Error('Invalid filter.');
      var n=key==='genre'?resolveGenre(value):key==='sort'?sort(value):key==='rating'?rating(value):year(value);
      if(key==='sort'&&value!==''&&!n)throw new Error('Invalid sort.');
      if(key==='genre'&&n===null)throw new Error('Invalid genre.');
      if(n)u.searchParams.set(key,String(n));else u.searchParams.delete(key);
      u.searchParams.delete('page');
      var state=read(u.href);
      if(state.from&&state.to&&state.from>state.to)throw new Error('The From year must be earlier than or equal to the To year.');
    }
    u.hash='';return u.href;
  }
  return {read:read,matches:matches,target:target,genres:genres,canonicalGenre:canonicalGenre};
}());
