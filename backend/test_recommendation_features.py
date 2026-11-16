"""Feature lookup against the title index, on synthetic titles; Gorse calls are captured, never sent."""
import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import recommendation_features
from history_index import norm

class FeatureLookupTests(unittest.TestCase):
    def test_imdb_id_is_found_by_name_without_reading_the_whole_index(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'amazon/personalized';root.mkdir(parents=True);(root.parent/'metadata').mkdir()
            db=sqlite3.connect(root.parent/'metadata/title-index.sqlite')
            db.executescript('create table titles(id text primary key,type text,title text,year integer,runtime integer,genres text);create table names(key text,id text,primary key(key,id));')
            rows=[('tt1','movie','Lone Film',2020,100,'Drama'),('tt2','tvSeries','Lone Film',2020,45,'Drama'),('tt3','movie','Twin',2019,100,'Drama'),('tt4','movie','Twin',2019,90,'Drama'),
                  ('tt5','movie','Der Film',2018,90,'Drama'),('tt6','tvEpisode','Solo Show',2021,30,'Comedy'),('tt7','tvSeries','Solo Show',2021,30,'Comedy')]
            db.executemany('insert into titles values (?,?,?,?,?,?)',rows);db.executemany('insert into names values (?,?)',[(norm(r[2]),r[0]) for r in rows]+[('otherfilm','tt5')]);db.commit();db.close()
            item=lambda ident,title,year,kind:dict(id=ident,title=title,year=year,type=kind,genres=['Drama'])
            catalogue={i['id']:i for i in [item('flixtor:movie:1','Lone Film','2020','movie'),item('flixtor:tv:2','Lone Film','2020','tv'),item('flixtor:movie:3','Twin','2019','movie'),
                                           item('flixtor:movie:5','Other Film','2018','movie'),item('flixtor:tv:7','Solo Show','2021','tv'),item('flixtor:movie:9','Absent','2020','movie')]}
            (root/'catalogue.json').write_text(json.dumps(catalogue))
            (root/'matches.json').write_text(json.dumps({'seeds':[{'item':dict(item('history:imdb:tt9','Kept','2001','movie'),metadata_id='tt9')}]}))
            sent=[]
            def gorse(path,payload=None,method=None):
                sent.append((path,payload));return {'recommend':{'ranker':{},'cache_size':1,'data_source':{}}} if payload is None else {}
            with patch('recommendation_features.call',gorse),patch('builtins.print'):recommendation_features.enrich_features(root)
            features=json.loads((root/'recommendation-features.json').read_text())
            self.assertEqual({k:v['source_id'] for k,v in features.items()},{'flixtor:movie:1':'tt1','flixtor:tv:2':'tt2','flixtor:movie:3':None,'flixtor:movie:5':None,'flixtor:tv:7':'tt7','flixtor:movie:9':None,'history:imdb:tt9':'tt9'},
                             'type and year decide; twins stay unknown; a name that is only an alternate title is not the title; an episode is not a series')
            uploaded=[p for path,p in sent if path=='/api/items'][0]
            self.assertEqual(len(uploaded),7);self.assertTrue(all(i['Labels']['metadata_vector'] for i in uploaded),'every item written to Gorse carries a vector')

class ApplyTests(unittest.TestCase):
    def test_every_item_the_matcher_writes_to_gorse_has_a_vector(self):
        import personalize,sys
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'amazon/personalized';out.mkdir(parents=True);staged=root/'history.sqlite'
            db=sqlite3.connect(staged);db.executescript('create table sessions(item_id,title,seconds_viewed,started_at,end_seconds);create table watchlist(item_id,title,added_at,deleted);create table items(item_id);')
            db.execute("insert into sessions values ('a','Example Film (2020)',1800,'2025-01-01',1700)");db.execute("insert into items values ('a')");db.commit();db.close()
            rows=root/'rows.json';rows.write_text(json.dumps([['/watch/movie/1/example-film','Example Film','2020','Drama','poster.jpg'],['/watch/tv/2/example-show','Example Show','2021','Comedy','poster.jpg']]))
            sent=[]
            def gorse(path,payload=None,method=None):
                sent.append((path,payload,method))
                if path.startswith('/api/user/') and path.endswith('/feedback'):return [dict(FeedbackType=f['FeedbackType'],ItemId=f['ItemId']) for p,f_list,m in sent if p=='/api/feedback' for f in f_list]
                if path.startswith('/api/user/'):return {'UserId':'ftv-amazon-import','Labels':{}}
                if path=='/api/dashboard/config':return {'recommend':{'data_source':{'positive_feedback_types':[]},'context_size':100}}
                return {}
            with patch('personalize.call',gorse),patch('builtins.print'),patch.object(sys,'argv',['personalize.py','--db',str(staged),'--catalogue',str(rows),'--out',str(out),'--apply']):personalize.main()
            items=[i for path,payload,_ in sent if path=='/api/items' for i in payload]
            self.assertEqual({i['ItemId'] for i in items},{'flixtor:movie:1','flixtor:tv:2'});self.assertTrue(all(len(i['Labels']['metadata_vector'])==len(recommendation_features.vector({})) for i in items))
            self.assertEqual(json.loads((out/'recommendation_import_report.json').read_text())['applied'],True)

if __name__=='__main__':unittest.main()
