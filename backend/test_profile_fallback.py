"""One unavailable viewer must not suppress healthy recommendation profiles."""
import json,tempfile,unittest
from pathlib import Path
from profiles import RecommendationProfiles

class ProfileFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.default=self.base/'default';self.directory=self.base/'profiles';self.directory.mkdir()
        self.ids=['ftv-netflix-'+'a'*16,'ftv-netflix-'+'b'*16]
        for root,ident in [(self.default,'existing-household')]+[(self.directory/i,i) for i in self.ids]:
            root.mkdir();(root/'matches.json').write_text(json.dumps({'profile':ident}));(root/'catalogue.json').write_text('{}')
        (self.directory/'profiles.json').write_text(json.dumps({'profiles':[{'id':ident,'name':'Example '+str(index)} for index,ident in enumerate(self.ids)]}))
        self.registry=RecommendationProfiles(self.default,self.directory)
    def tearDown(self):self.temp.cleanup()
    def test_household_failure_does_not_suppress_healthy_named_profiles(self):
        attempted=[]
        def recommend(root,store):
            attempted.append(Path(root))
            if Path(root)==self.default:raise OSError('Synthetic household outage')
            return {'engine':'gorse','items':[{'title':'Synthetic pick'}],'scope':store.profile()}
        result=self.registry.bundle(recommend)
        self.assertEqual(result['engine'],'gorse')
        named={p['id']:p for p in result['profiles'] if p['id'] in self.ids}
        self.assertEqual(set(named),set(self.ids))
        self.assertTrue(all(len(p['items'])==1 for p in named.values()))
        self.assertEqual(len(attempted),3)
    def test_named_failure_does_not_suppress_household_or_other_viewer(self):
        def recommend(root,store):
            if Path(root)==self.directory/self.ids[0]:raise OSError('Synthetic one-viewer outage')
            return {'engine':'gorse','items':[{'title':'Synthetic pick'}]}
        result=self.registry.bundle(recommend);packs={p['id']:p for p in result['profiles']}
        self.assertEqual(len(result['items']),1)
        self.assertEqual(packs[self.ids[0]]['items'],[])
        self.assertEqual(len(packs[self.ids[1]]['items']),1)
    def test_no_registry_preserves_legacy_success_shape(self):
        registry=RecommendationProfiles(self.default,self.base/'absent-registry')
        expected={'engine':'gorse','items':[],'scope':'legacy','seedCount':4}
        self.assertEqual(registry.bundle(lambda *_:dict(expected)),expected)
if __name__=='__main__':unittest.main()
