window.FTV_PREVIEW = [
  ['MobLand','2025','Crime, Drama','5Xc7WpWsgflfgEMoBlf9TmWhfbH.jpg','/watch/tv/13871234/mobland'],
  ['Heart of the Beast','2026','Adventure, Thriller','1ApfSA8JTqeha3GTFEY8syV4auq.jpg','/watch/movie/70747690/heart-of-the-beast'],
  ['Tulsa King','2022','Crime, Drama, Comedy','fwTv3RPRAIy0maOMns5eYRRwnDk.jpg','/watch/tv/8586706/tulsa-king'],
  ['The Mongoose','2026','Action, Thriller','eSS5mvSG84UUuvtbHel5Yu3Wik4.jpg','/watch/movie/72473354/the-mongoose'],
  ['Primetime','2026','Thriller, Drama','lmrulvLbmaejTix1YaMxo1oGhH1.jpg','/watch/movie/77023594/primetime'],
  ['VisionQuest','2026','Sci-Fi-Fantasy, Drama','WGyAyBPncfuu8MZhLY9RtfZPM0.jpg','/watch/tv/11949850/visionquest'],
  ['Resident Evil','2026','Horror, Science-Fiction, Adventure','diI1NMZ9lkzCUmdDzwyk4Qcqmt5.jpg','/watch/movie/79699930/resident-evil'],
  ['Dexter: Resurrection','2025','Crime, Drama, Mystery','o2Oyi3boT100bY5kCP4MBiTeetO.jpg','/watch/tv/14554058/dexter-resurrection'],
  ['Chicago P.D.','2014','Crime, Drama','w7R4ooo2IbOfBKOoMDwaiMGsNQf.jpg','/watch/tv/3294122/chicago-p-d'],
  ['Nocturne','2026','Crime, Drama, Mystery','nyvXVcPnHEwVmqCdzjjCsu1jqhm.jpg','/watch/tv/16392650/nocturne'],
  ['Black Doves','2024','Action-Adventure, Mystery, Crime','srlsyEfIBz2MNWBndVc3opOaNGS.jpg','/watch/tv/12620330/black-doves'],
  ['The Greatest','2026','Drama','hu4jco5AOs8NSIctuc9KsRyuSg8.jpg','/watch/tv/14502154/the-greatest']
].map(function (a) { return {title:a[0],year:a[1],meta:a[2],image:'https://img.xcdn.to/t/p/w342/'+a[3],url:a[4]}; });
// Real episode labels captured from the visible MobLand series page.
window.FTV_PREVIEW[0].description='Two mob families clash in a war that threatens to topple empires and lives.';
window.FTV_PREVIEW[0].rating='8.6';
window.FTV_PREVIEW[0].episodes=[
  ['Stick or Twist','Jigsaw Puzzle','Plan B','Rat Trap','Funeral for a Friend','Antwerp Blues','The Crossroads','Helter Skelter','Beggars Banquet','The Beast in Me'],
  ['I Wanna Be Your Dog','Song 2','Bonzo Goes to Bitburg','Blank Curtain','Birdland','A Different Corner','Ace of Spades',"We Don't Talk Anymore"]
].reduce(function(out,titles,index){return out.concat(titles.map(function(title,n){return {season:index+1,number:n+1,title:title};}));},[]);
