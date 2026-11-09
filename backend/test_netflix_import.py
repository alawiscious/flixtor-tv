import csv,io,json,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from netflix_import import stage,prepare,Resolver,rating,seconds,profile_id

class NetflixImportTests(unittest.TestCase):
    def test_rating_dictionary(self):
        for thumb,expected in [('0','clear'),('1','dislike'),('2','like'),('3','like')]:self.assertEqual(rating('thumb','5',thumb),expected)
        for star,expected in [('0','clear'),('-1','dislike'),('-2','unwatched'),('1','dislike'),('2','dislike'),('3','clear'),('4','like'),('5','like')]:self.assertEqual(rating('star',star,'2'),expected)
        self.assertEqual(rating('star','bad','2'),'unknown')
    def test_durations(self):
        self.assertEqual(seconds('01:02:03'),3723)
        for value in ['bad','-1:00:00','00:99:00','00:00:90']:self.assertIsNone(seconds(value))
    def test_private_profile_isolation_idempotency_and_matching(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'export.zip'
            def csv_text(rows):
                buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);return buf.getvalue()
            def view(name,title,kind=''):
                return {'Profile Name':name,'Title':title,'Start Time':'2026-01-01 12:00:00','Duration':'00:30:00','Supplemental Video Type':kind,'Bookmark':'00:30:00','Latest Bookmark':'00:30:00'}
            views=[view('Alice','Example Show: Season 2: Episode 14'),view('Alice','Example Show: Season 2: Episode 14'),view('Bob','Other Film'),view('Alice','Other Film','TRAILER'),view('Unknown','Other Film')]
            ratings=[{'Profile Name':'Alice','Title Name':'Example Show','Event Utc Ts':'2026-02-01 12:00:00','Rating Type':'thumb','Star Value':'','Thumbs Value':'2'}, {'Profile Name':'Bob','Title Name':'Other Film','Event Utc Ts':'2026-02-01 12:00:00','Rating Type':'star','Star Value':'-2','Thumbs Value':'2'}]
            with zipfile.ZipFile(archive,'w') as z:
                for filename,rows in [('PROFILES/Profiles.csv',[{'Profile Name':'Alice','Email Address':'private@example.test','Date Of Birth':'private'},{'Profile Name':'Bob','Email Address':'private2@example.test','Date Of Birth':'private'}]),('CONTENT_INTERACTION/ViewingActivity.csv',views),('CONTENT_INTERACTION/Ratings.csv',ratings),('CONTENT_INTERACTION/MyList.csv',[{'Profile Name':'Alice','Title Name':'Other Film','Utc Title Add Date':'2026-02-02 12:00:00'}])]:z.writestr('account/'+filename,csv_text(rows))
                z.writestr('../../escape','never extracted')
            db,unknown=stage(archive,root/'stage.sqlite');self.assertEqual(unknown,1);n=db.execute('select count(*) from events').fetchone()[0];db.close()
            db,unknown=stage(archive,root/'stage.sqlite');self.assertEqual(db.execute('select count(*) from events').fetchone()[0],n);self.assertEqual(db.execute('select count(*) from imports').fetchone()[0],1)
            self.assertEqual([r[1] for r in db.execute('pragma table_info(profiles)')],['id','name']);self.assertFalse((root.parent/'escape').exists())
            metadata=root/'metadata.sqlite';m=sqlite3.connect(metadata);m.execute('create table titles(id text,type text,title text,year integer,genres text)');m.executemany('insert into titles values(?,?,?,?,?)',[('tt1','tvSeries','Example Show',2020,'Action'),('tt2','movie','Other Film',2020,'Drama'),('tt3','movie','Ambiguous',1990,'Drama'),('tt4','movie','Ambiguous',2010,'Drama')]);m.commit();m.close()
            items={ 'flixtor:tv:1':dict(id='flixtor:tv:1',title='Example Show',type='tv',year='2020',genres=['Action'],url='https://flixtor.to/watch/tv/1/example',image=''), 'flixtor:movie:2':dict(id='flixtor:movie:2',title='Other Film',type='movie',year='2020',genres=['Drama'],url='https://flixtor.to/watch/movie/2/other',image='')}
            resolver=Resolver(items,metadata);self.assertIsNone(resolver.resolve('Ambiguous','2026-01-01'));self.assertIsNone(resolver.resolve('Missing Film','2026-01-01'))
            reports,_=prepare(db,items,resolver,root/'profiles');db.close()
            alice=json.loads((root/'profiles'/profile_id('Alice')/'matches.json').read_text());bob=json.loads((root/'profiles'/profile_id('Bob')/'matches.json').read_text())
            self.assertEqual(alice['seen'],['flixtor:tv:1']);self.assertEqual(bob['seen'],[]);self.assertEqual(bob['seeds'],[]);self.assertEqual(next(r for r in reports if r['name']=='Alice')['supplemental_excluded'],1)
            self.assertEqual({r['UserId'] for r in json.loads((root/'profiles'/profile_id('Bob')/'gorse-feedback.json').read_text())},{profile_id('Bob')})
            self.assertTrue(any(r['FeedbackType']=='recommend_unwatched' for r in json.loads((root/'profiles'/profile_id('Bob')/'gorse-feedback.json').read_text())))
if __name__=='__main__':unittest.main()
