import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from personalize import catalogue,resolve,match_history
from relay import recommendation_payload,CatalogueSync

class PersonalizationTests(unittest.TestCase):
    def setUp(self):
        self.items=catalogue([
          ['/watch/tv/1/fleabag','Fleabag','2016','Comedy, Drama','a.jpg'],
          ['/watch/tv/2/battlestar-galactica','Battlestar Galactica','2004','Drama','b.jpg'],
          ['/watch/movie/3/fight-club','Fight Club','1999','Drama, Thriller','c.jpg'],
          ['/watch/movie/4/pilot','Pilot','2020','Drama','d.jpg']])
    def test_conservative_mapping(self):
        self.assertEqual(resolve('Fleabag Season 1 (4K UHD)',self.items)['id'],'flixtor:tv:1')
        self.assertIsNone(resolve('Battlestar Galactica Season 1',self.items))
        self.assertIsNone(resolve('Fleabag (2020) - Season 1',self.items))
        self.assertEqual(resolve('Battlestar Galactica (2004) - Season 1',self.items)['id'],'flixtor:tv:2')
        self.assertIsNone(resolve('Fleabag Season 1',catalogue([['/watch/tv/1/fleabag','Fleabag','2016','Drama','a.jpg'],['/watch/tv/2/fleabag','Fleabag','2016','Comedy','b.jpg']])))
    def test_does_not_turn_episodes_into_movies_or_deleted_adds_into_interest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.db';c=sqlite3.connect(p)
            c.executescript('create table watchlist(item_id,title,added_at,deleted); create table sessions(item_id,title,seconds_viewed,started_at);')
            c.execute('insert into watchlist values (?,?,?,?)',('a','Fleabag Season 1','2020-01-01T00:00:00Z',1))
            c.executemany('insert into sessions values (?,?,?,?)',[('x','Pilot',1800,'2020-01-01T00:00:00Z'),('y','Fight Club',1800,'2020-01-01T00:00:00Z')]);c.commit();c.close()
            seeds,seen,review=match_history(p,self.items)
            self.assertEqual(set(seeds),{'flixtor:movie:3'});self.assertEqual(set(seen),{'flixtor:movie:3'})
    def test_catalogue_ingestion_only_accepts_public_card_schema(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'catalogue.json').write_text('{}')
            sync=CatalogueSync(p,'unused.db')
            with patch('threading.Timer'):
                count=sync.add([['/watch/tv/1/fleabag','Fleabag','2016','Comedy, Drama','https://img.xcdn.to/t/p/w342/abc.jpg'],['/admin','bad','2016','Drama','https://evil.example/test.jpg']])
            self.assertEqual(count,1)
            self.assertEqual(set(sync.pending),{'flixtor:tv:1'})
            with self.assertRaises(ValueError):sync.add({'history':'private'})
    def test_relay_filters_seen_unknown_and_seeds(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'catalogue.json').write_text(json.dumps(self.items))
            (p/'matches.json').write_text(json.dumps({'profile':'test','seen':['flixtor:movie:3'],'seeds':[{'item':self.items['flixtor:tv:1']}]}))
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self):return json.dumps(['unknown','flixtor:movie:3','flixtor:tv:1','flixtor:tv:2']).encode()
            with patch('urllib.request.urlopen',return_value=Response()):
                result=recommendation_payload(p)
            self.assertEqual([i['id'] for i in result['items']],['flixtor:tv:2'])
            self.assertIn('Similar genres',result['items'][0]['reason'])
            self.assertNotIn('seeds',result)

if __name__=='__main__':unittest.main()
