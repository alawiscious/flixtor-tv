import sqlite3,tempfile,unittest
from pathlib import Path
from enrich_history import enrich,genre_tags

class MetadataHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=self.root/'history.sqlite';c=sqlite3.connect(self.db)
        c.executescript('create table sessions(item_id,title,seconds_viewed,started_at,end_seconds);create table watch_summaries(item_id,title,seconds_watched,last_watched_at,deleted);create table watchlist(item_id,title,added_at,deleted);')
        c.close();self.index=self.root/'index.sqlite';c=sqlite3.connect(self.index)
        c.executescript('create table titles(id primary key,type,title,year,runtime,genres);create table names(key,id);create table episodes(id,parent,season,episode);create table votes(id,votes);')
        rows=[('movie','movie','Long Movie',2020,100,'Drama,Sci-Fi'),('show','tvSeries','Example Series',2019,45,'Drama'),('ep1','tvEpisode','Unique First Episode',2019,45,'Drama'),('ep2','tvEpisode','Unique Second Episode',2019,45,'Drama'),('review','tvEpisode','Long Movie',2020,10,'Talk-Show'),('other','movie','Ambiguous Title',2010,100,'Drama'),('remake','movie','Ambiguous Title',2020,100,'Drama')]
        c.executemany('insert into titles values (?,?,?,?,?,?)',rows)
        from history_index import norm
        c.executemany('insert into names values (?,?)',[(norm(r[2]),r[0]) for r in rows])
        c.executemany('insert into episodes values (?,?,?,?)',[('ep1','show',1,1),('ep2','show',1,2),('review','podcast',1,1)])
        c.execute('insert into votes values (?,?)',('movie',50000));c.commit();c.close()
    def tearDown(self):self.tmp.cleanup()
    def add(self,table,row):
        c=sqlite3.connect(self.db);c.execute('insert into '+table+' values ('+','.join('?' for _ in row)+')',row);c.commit();c.close()
    def test_history_does_not_require_a_playable_match(self):
        self.add('sessions',('m','Long Movie',1800,'2025-01-01',1800))
        r=enrich(self.db,self.index,{})
        self.assertEqual(set(r['seeds']),{'history:imdb:movie'})
        self.assertEqual(r['seeds']['history:imdb:movie']['item']['genres'],['Drama','Science-Fiction'])
        self.assertEqual(r['seen'],set())
    def test_playback_and_summary_are_not_added_to_cross_interest_threshold(self):
        self.add('sessions',('m','Long Movie',700,'2025-01-01',700))
        self.add('watch_summaries',('s','Long Movie',700,'2025-01-01',0))
        self.assertEqual(enrich(self.db,self.index,{})['seeds'],{})
    def test_episode_needs_independent_parent_support_and_rolls_up(self):
        self.add('sessions',('e1','Unique First Episode',1800,'2025-01-01',1800))
        self.assertEqual(enrich(self.db,self.index,{})['seeds'],{})
        self.add('sessions',('e2','Unique Second Episode',1800,'2025-01-02',1800))
        r=enrich(self.db,self.index,{})
        self.assertEqual(set(r['seeds']),{'history:imdb:show'})
        self.assertEqual(r['seeds']['history:imdb:show']['episode_title_count'],2)
    def test_compound_episode_series_season_title_and_summary_deduplicate(self):
        self.add('sessions',('e1','Unique First Episode-Example Series - Season 1',700,'2025-01-01',700))
        self.add('watch_summaries',('s','Unique First Episode',700,'2025-01-01',0))
        result=enrich(self.db,self.index,{})
        self.assertEqual(result['report']['resolved_observations'],2)
        self.assertEqual(result['seeds'],{}) # not 1400 seconds
    def test_remakes_are_not_guessed(self):
        self.add('sessions',('m','Ambiguous Title',1800,'2025-01-01',1800))
        self.assertEqual(enrich(self.db,self.index,{})['seeds'],{})
    def test_explicit_like_is_preserved_and_dislike_blocks_interest(self):
        feedback=[{'Entity Type':'Movie','Feedback Type':'Like','Feedback Date':'2025-01-01','Title Name':'Long Movie'}]
        r=enrich(self.db,self.index,{},feedback)
        self.assertEqual(r['seeds']['history:imdb:movie']['feedback_type'],'like')
        feedback.append(dict(feedback[0],**{'Feedback Type':'Dislike','Feedback Date':'2025-02-01'}))
        r=enrich(self.db,self.index,{},feedback)
        self.assertEqual(r['seeds'],{});self.assertEqual(r['excluded'],{'history:imdb:movie'})
    def test_deleted_summary_does_not_supply_interest(self):
        self.add('watch_summaries',('s','Long Movie',1800,'2025-01-01',1))
        self.assertEqual(enrich(self.db,self.index,{})['seeds'],{})
    def test_bulk_index_build_retains_parent_and_vote_metadata(self):
        import gzip
        from history_index import build_index
        basics=self.root/'basics.gz';episodes=self.root/'episodes.gz';ratings=self.root/'ratings.gz';output=self.root/'built.sqlite'
        with gzip.open(basics,'wt') as f:f.write('tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\nshow\ttvSeries\tExample Series\tExample Series\t0\t2019\t\\N\t45\tDrama\nep1\ttvEpisode\tUnique First Episode\tUnique First Episode\t0\t2019\t\\N\t45\tDrama\n')
        with gzip.open(episodes,'wt') as f:f.write('tconst\tparentTconst\tseasonNumber\tepisodeNumber\nep1\tshow\t1\t1\n')
        with gzip.open(ratings,'wt') as f:f.write('tconst\taverageRating\tnumVotes\nep1\t8.0\t2000\n')
        build_index(basics,episodes,output,{'uniquefirstepisode'},ratings)
        c=sqlite3.connect(output)
        self.assertEqual(c.execute('select parent from episodes where id="ep1"').fetchone()[0],'show')
        self.assertEqual(c.execute('select votes from votes where id="ep1"').fetchone()[0],2000)
        self.assertEqual(c.execute('select title from titles where id="show"').fetchone()[0],'Example Series')
        c.close()
    def test_genre_taxonomies_share_tags(self):
        self.assertEqual(genre_tags(['Sci-Fi','Sci-Fi-Fantasy','TV-Movie']),['Science-Fiction','Fantasy'])

if __name__=='__main__':unittest.main()
