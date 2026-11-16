"""Complete index + Netflix title matching, on synthetic titles only."""
import gzip,json,sqlite3,tempfile,unittest
from pathlib import Path
from history_index import build_index,title_keys,norm
from netflix_import import Resolver,splits

BASICS=[('s1','tvSeries','Twin Show','Twin Show','0','2010','\\N','45','Drama'),('s2','tvSeries','Twin Show','Twin Show','0','2020','\\N','45','Drama'),
        ('s3','tvSeries','Solo Show','Solo Show','0','2015','\\N','30','Comedy'),('s4','tvSeries','Unwatched Show','Unwatched Show','0','2015','\\N','30','Comedy'),
        ('m1','movie','Solo Show','Solo Show','0','2001','\\N','100','Drama'),('m2','movie','Lone Film','Der Einzelfilm','0','2012','\\N','90','Drama'),
        ('m3','movie','Remake','Remake','0','1990','\\N','90','Drama'),('m4','movie','Remake','Remake','0','2015','\\N','95','Drama'),('x1','movie','Adult Film','Adult Film','1','2012','\\N','90','Adult'),
        ('e1','tvEpisode','First Light','First Light','0','2010','\\N','45','Drama'),('e2','tvEpisode','Second Wind','Second Wind','0','2010','\\N','45','Drama'),
        ('e3','tvEpisode','Other Start','Other Start','0','2020','\\N','45','Drama'),('e4','tvEpisode','Opening','Opening','0','2015','\\N','30','Comedy'),
        ('e5','tvEpisode','Closing','Closing','0','2015','\\N','30','Comedy'),('e6','tvEpisode','Never Seen','Never Seen','0','2015','\\N','30','Comedy'),('h1','short','Tiny Short','Tiny Short','0','2015','\\N','5','Short')]
EPISODES=[('e1','s1','1','1'),('e2','s1','1','2'),('e3','s2','1','1'),('e4','s3','1','1'),('e5','s3','1','2'),('e6','s4','1','1')]
WATCHED=['Twin Show: Season 1: First Light (Episode 1)','Twin Show: Season 1: Second Wind (Episode 2)','Solo Show: Opening (Episode 1)','Solo Show: Limited Series: Closing (Episode 2)','Lone Film','Remake','Solo Show']

def write(path,header,rows):
    with gzip.open(path,'wt',encoding='utf-8') as f:f.write(header+'\n'+''.join('\t'.join(r)+'\n' for r in rows))

class MatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name);cls.index=root/'index.sqlite'
        write(root/'basics.gz','tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres',BASICS)
        write(root/'episodes.gz','tconst\tparentTconst\tseasonNumber\tepisodeNumber',EPISODES)
        write(root/'ratings.gz','tconst\taverageRating\tnumVotes',[('s1','8.0','5000'),('m2','7.0','900')])
        keys=set()
        for title in WATCHED:keys.update(title_keys(title))
        build_index(root/'basics.gz',root/'episodes.gz',cls.index,keys,root/'ratings.gz',[{'source':'synthetic','titles':len(WATCHED)}])
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def resolver(self,items=None):
        r=Resolver(items or {},self.index);r.learn(WATCHED);return r
    def test_keys_cover_every_way_a_title_can_be_looked_up(self):
        self.assertIn('twinshow',title_keys('Twin Show: Season 1: First Light (Episode 1)'));self.assertIn('ab',title_keys('A: B: Name (Episode 5)'))
        self.assertIn('lonefilm',title_keys('Lone Film'));self.assertEqual(title_keys(' : '),set())
    def test_index_names_all_films_and_series_and_lists_whole_history_series(self):
        db=sqlite3.connect(self.index);names=lambda key:{r[0] for r in db.execute('select id from names where key=?',(key,))}
        self.assertEqual(names('remake'),{'m3','m4'});self.assertEqual(names('dereinzelfilm'),{'m2'},'original titles are names too')
        self.assertEqual(names('unwatchedshow'),{'s4'},'a series nobody watched is still findable by name')
        self.assertEqual(names('adultfilm'),set());self.assertEqual(names('tinyshort'),set(),'shorts stay out unless history names them')
        self.assertEqual({r[0] for r in db.execute("select id from episodes where parent='s1'")},{'e1','e2'},'full list, although only the names were watched')
        self.assertEqual(names('otherstart'),{'e3'},'episodes of a same-named series are listed so they can be told apart')
        self.assertEqual(db.execute("select count(*) from episodes where parent='s4'").fetchone()[0],0,'episode lists are limited to history series')
        meta=dict(db.execute('select key,value from meta'));self.assertIn('every non-adult movie',meta['coverage']);self.assertEqual(json.loads(meta['sources'])[0]['source'],'synthetic')
        self.assertEqual(db.execute("select votes from votes where id='s1'").fetchone()[0],5000);db.close()
    def test_export_episode_tag_and_season_marker_are_read_as_facts(self):
        self.assertEqual(splits('Twin Show: Season 2: A: B (Episode 3)'),[('Twin Show','A: B',True,2,3)])
        self.assertEqual(splits('Solo Show: Limited Series: Closing (Episode 2)'),[('Solo Show','Closing',True,1,2)])
        self.assertEqual(splits('A: B: Name (Episode 5)'),[('A: B','Name',True,None,5),('A','B: Name',True,None,5)])
        self.assertEqual(splits('Film: Subtitle'),[('Film: Subtitle',None,False,None,None),('Film','Subtitle',False,None,None)])
    def test_same_named_series_is_settled_only_by_watched_episode_names(self):
        r=self.resolver();item=r.resolve('Twin Show: Season 1: First Light (Episode 1)','2024-01-01')
        self.assertEqual(item['id'],'history:imdb:s1');self.assertEqual(r.methods[('Twin Show: Season 1: First Light (Episode 1)','2024')],'episode names among same-named titles')
        self.assertEqual(r.episode('Twin Show: Season 1: First Light (Episode 1)','2024-01-01'),(1,1))
        bare=Resolver({},self.index);self.assertIsNone(bare.resolve('Twin Show: Season 1: First Light (Episode 1)','2024-01-01'),'no evidence learned, so no guess')
    def test_episode_tag_makes_the_prefix_a_series_and_fills_a_missing_season(self):
        r=self.resolver();title='Solo Show: Opening (Episode 1)';item=r.resolve(title,'2024-01-01')
        self.assertEqual((item['id'],item['type']),('history:imdb:s3','tv'),'the film of the same name is not an episode');self.assertEqual(r.episode(title,'2024-01-01'),(1,1))
        self.assertEqual(r.total_episodes(item),2)
    def test_single_title_prefers_the_one_film_and_leaves_remakes_unresolved(self):
        r=self.resolver()
        self.assertEqual(r.resolve('Solo Show','2024-01-01')['id'],'history:imdb:m1');self.assertEqual(r.methods[('Solo Show','2024')],'unique movie title')
        self.assertEqual(r.resolve('Lone Film','2024-01-01')['id'],'history:imdb:m2');self.assertIsNone(r.resolve('Remake','2024-01-01'))
        self.assertEqual(r.resolve('Remake','2000-01-01')['id'],'history:imdb:m3','a title released after the viewing date cannot be what was watched')
        self.assertIsNone(r.resolve('Unknown: Something Else','2024-01-01'));self.assertIsNone(r.episode('Lone Film','2024-01-01'))
    def test_catalogue_identity_is_kept_for_a_resolved_title(self):
        items={'flixtor:tv:9':dict(id='flixtor:tv:9',title='Solo Show',type='tv',year='2015',genres=['Comedy'])}
        r=self.resolver(items);title='Solo Show: Limited Series: Closing (Episode 2)'
        self.assertEqual(r.resolve(title,'2024-01-01')['id'],'flixtor:tv:9');self.assertEqual(r.episode(title,'2024-01-01'),(1,2))

if __name__=='__main__':unittest.main()
