import json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from feedback import FeedbackStore
from recommendation_features import vector

class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'matches.json').write_text(json.dumps({'profile':'test'}));(self.root/'catalogue.json').write_text(json.dumps({'flixtor:movie:1':{'title':'Fixture'}}));self.store=FeedbackStore(self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_opinion_and_watch_state_are_independent_and_survive_restart(self):
        with patch('feedback.gorse',return_value={}):
            self.store.save({'itemId':'flixtor:movie:1','preference':'like'})
            self.store.save({'itemId':'flixtor:movie:1','watched':True})
        state=FeedbackStore(self.root).states()['flixtor:movie:1']
        self.assertEqual(state['preference'],'like');self.assertIs(state['watched'],True);self.assertFalse(state['syncPending'])
    def test_outage_retains_feedback_and_retries_after_restart(self):
        with patch('feedback.gorse',side_effect=urllib.error.URLError('offline')):
            self.assertTrue(self.store.save({'itemId':'flixtor:movie:1','preference':'dislike'})['syncPending'])
        again=FeedbackStore(self.root)
        with patch('feedback.gorse',return_value={}):again.sync()
        self.assertFalse(again.states()['flixtor:movie:1']['syncPending'])
    def test_changed_preference_removes_opposite_signal(self):
        with patch('feedback.gorse',return_value={}) as api:
            self.store.save({'itemId':'flixtor:movie:1','preference':'dislike','watched':False})
        self.assertTrue(any('/recommend_like/' in args[0][0] and args[1].get('method')=='DELETE' for args in api.call_args_list))
        values=next(args[0][1] for args in api.call_args_list if args[0][0]=='/api/feedback')
        self.assertEqual({v['FeedbackType'] for v in values},{'recommend_dislike','recommend_unwatched'})
    def test_rejects_unknown_item_invalid_type_and_profile_override(self):
        for data in [{'itemId':'other','watched':True},{'itemId':'flixtor:movie:1','watched':1},{'itemId':'flixtor:movie:1','profile':'other','preference':'like'}]:
            with self.assertRaises(ValueError):self.store.save(data)
    def test_undo_is_not_a_negative_preference(self):
        with patch('feedback.gorse',return_value={}):state=self.store.save({'itemId':'flixtor:movie:1','preference':'clear','watched':None})
        self.assertEqual(state['preference'],'clear');self.assertIsNone(state['watched'])
    def test_metadata_vectors_are_normalized_and_distinguish_era_type(self):
        a=vector({'genres':['Drama'],'year':'2020','type':'movie'});b=vector({'genres':['Drama'],'year':'1950','type':'tv'})
        self.assertAlmostEqual(sum(v*v for v in a),1,places=5);self.assertNotEqual(a,b)

if __name__=='__main__':unittest.main()
