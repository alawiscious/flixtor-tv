"""Seen + rating (love / like / dislike / hate): storage, migration, Gorse sync and re-ranking weights."""
import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from feedback import FeedbackStore,RATINGS
from relay import recommendation_payload,feedback_weight,SEED_WEIGHTS,NEGATIVE_WEIGHTS

def item(n,genres,kind='movie'):
    return {'id':'flixtor:%s:%d'%(kind,n),'title':'T%d'%n,'year':'2020','type':kind,'genres':genres,'url':'https://flixtor.to/watch/%s/%d/t'%(kind,n),'image':'https://img.xcdn.to/t/p/w342/%d.jpg'%n,'meta':', '.join(genres)}

class RatingStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'matches.json').write_text(json.dumps({'profile':'p'}));(self.root/'catalogue.json').write_text(json.dumps({'flixtor:movie:1':{'title':'A'}}))
    def tearDown(self):self.tmp.cleanup()
    def test_rating_marks_seen_survives_restart_and_clears_independently(self):
        store=FeedbackStore(self.root)
        with patch('feedback.gorse',return_value={}):state=store.save({'itemId':'flixtor:movie:1','rating':'love'})
        self.assertEqual(state['rating'],'love');self.assertIs(state['watched'],True,'a rating is a fact the title was seen')
        with patch('feedback.gorse',return_value={}):store.save({'itemId':'flixtor:movie:1','rating':'love','watched':False})
        self.assertIs(FeedbackStore(self.root).states()['flixtor:movie:1']['watched'],True,'rating wins over a contradictory not-watched')
        with patch('feedback.gorse',return_value={}):state=store.save({'itemId':'flixtor:movie:1','rating':None})
        self.assertIsNone(state['rating']);self.assertIs(state['watched'],True,'clearing the rating keeps the seen fact');self.assertEqual(state['preference'],'clear')
    def test_invalid_rating_and_fields_rejected(self):
        store=FeedbackStore(self.root)
        for bad in [{'itemId':'flixtor:movie:1','rating':'meh'},{'itemId':'flixtor:movie:1','rating':5},{'itemId':'flixtor:movie:1','stars':5}]:
            with self.assertRaises(ValueError):store.save(bad)
    def test_sync_sends_one_rating_type_and_removes_the_others(self):
        store=FeedbackStore(self.root)
        with patch('feedback.gorse',return_value={}) as api:store.save({'itemId':'flixtor:movie:1','rating':'hate'})
        sent=next(c[0][1] for c in api.call_args_list if c[0][0]=='/api/feedback')
        self.assertEqual({v['FeedbackType'] for v in sent},{'rating_hate','recommend_watched'})
        deleted={c[0][0].split('/')[3] for c in api.call_args_list if c[1].get('method')=='DELETE'}
        self.assertTrue({'rating_love','rating_like','rating_dislike'}<=deleted);self.assertNotIn('rating_hate',deleted)
    def test_existing_database_is_migrated_in_place(self):
        db=sqlite3.connect(self.root/'user-feedback.sqlite')
        db.execute('create table feedback(profile text,item text,preference text not null default "clear",watched integer,at text not null,synced integer not null default 0,primary key(profile,item))')
        db.execute("insert into feedback values ('p','flixtor:movie:1','like',0,'2026-01-01T00:00:00Z',1)");db.commit();db.close()
        state=FeedbackStore(self.root).states()['flixtor:movie:1']
        self.assertEqual((state['preference'],state['watched'],state['rating']),('like',False,None))

class RatingRankingTests(unittest.TestCase):
    def test_weight_table_is_the_single_resolver(self):
        self.assertEqual(feedback_weight({'rating':'love','preference':'clear'},SEED_WEIGHTS),6)
        self.assertEqual(feedback_weight({'rating':None,'preference':'like'},SEED_WEIGHTS),4)
        self.assertEqual(feedback_weight({'rating':'hate','preference':'clear'},NEGATIVE_WEIGHTS),2)
        self.assertEqual(feedback_weight({'rating':'like','preference':'clear'},NEGATIVE_WEIGHTS),0)
        self.assertEqual(set(RATINGS),{'love','like','dislike','hate'})
    def rank(self,states):
        items={i['id']:i for i in [item(1,['Horror']),item(2,['Comedy']),item(3,['Horror']),item(4,['Comedy']),item(5,['Drama'])]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'catalogue.json').write_text(json.dumps(items))
            (p/'matches.json').write_text(json.dumps({'profile':'p','seen':[],'seeds':[{'item':items['flixtor:movie:5'],'at':'2026-01-01T00:00:00Z'}]}))
            class Store:
                catalogue_root=p
                def states(self):return {k:{**dict(preference='clear',watched=None,rating=None,syncPending=False),**v} for k,v in states.items()}
            class Response:
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def read(self):return json.dumps(['flixtor:movie:3','flixtor:movie:4']).encode()
            with patch('urllib.request.urlopen',return_value=Response()):return [i['id'] for i in recommendation_payload(p,Store())['items']]
    def test_loved_title_pulls_similar_titles_up_and_hated_title_pushes_them_down(self):
        self.assertEqual(self.rank({'flixtor:movie:1':{'rating':'love','watched':True}})[0],'flixtor:movie:3','loved horror lifts horror')
        self.assertEqual(self.rank({'flixtor:movie:2':{'rating':'love','watched':True}})[0],'flixtor:movie:4','loved comedy lifts comedy')
        self.assertEqual(self.rank({'flixtor:movie:1':{'rating':'hate','watched':True}})[0],'flixtor:movie:4','hated horror sinks horror')
        self.assertNotIn('flixtor:movie:1',self.rank({'flixtor:movie:1':{'rating':'love','watched':True}}),'rated titles are seen, never recommended')

if __name__=='__main__':unittest.main()
