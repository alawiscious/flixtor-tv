import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from profiles import RecommendationProfiles

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.default=self.root/'household';self.directory=self.root/'profiles';self.directory.mkdir()
        self.ids=['ftv-netflix-'+'a'*16,'ftv-netflix-'+'b'*16]
        for root,ident in [(self.default,'old-household')]+[(self.directory/i,i) for i in self.ids]:
            root.mkdir();(root/'matches.json').write_text(json.dumps({'profile':ident}));(root/'catalogue.json').write_text(json.dumps({'flixtor:movie:1':{'title':'Example'}}))
        (self.directory/'profiles.json').write_text(json.dumps({'profiles':[{'id':i,'name':name} for i,name in zip(self.ids,['Example A','Example B'])]}));self.registry=RecommendationProfiles(self.default,self.directory)
    def tearDown(self):self.temp.cleanup()
    def test_feedback_does_not_leak_between_profiles(self):
        with patch('feedback.gorse',return_value={}):self.registry.save({'profileId':self.ids[0],'itemId':'flixtor:movie:1','preference':'like'})
        self.assertEqual(self.registry.store(self.ids[0]).states()['flixtor:movie:1']['preference'],'like');self.assertEqual(self.registry.store(self.ids[1]).states(),{});self.assertEqual(self.registry.store().states(),{})
    def test_rejects_unknown_profile_and_traversal(self):
        for ident in ['../../private',self.ids[0]+'/../other','ftv-netflix-'+'c'*16,[],None]:
            with self.assertRaises(ValueError):self.registry.save({'profileId':ident,'itemId':'flixtor:movie:1','preference':'like'})
    def test_bundle_keeps_legacy_fields_and_no_raw_history(self):
        def rec(root,store):return {'engine':'gorse','items':[],'scope':store.profile()}
        result=self.registry.bundle(rec);self.assertEqual(result['scope'],'old-household');self.assertEqual([p['id'] for p in result['profiles']],['household']+self.ids);self.assertFalse(any('root' in p for p in result['profiles']))
    def test_missing_registry_preserves_old_response(self):
        r=RecommendationProfiles(self.default,self.root/'missing');self.assertEqual(r.bundle(lambda *_:{'engine':'gorse','items':[]}),{'engine':'gorse','items':[]})
if __name__=='__main__':unittest.main()
