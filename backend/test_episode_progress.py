import contextlib,io,json,stat,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from episode_progress import EpisodeProgressStore,main
from profiles import RecommendationProfiles

SERIES='flixtor:tv:4018954'
SECOND='flixtor:tv:2'

class EpisodeProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.default=self.make_root(self.base/'household','household-user')
        self.directory=self.base/'profiles';self.directory.mkdir()
        self.ids=['ftv-netflix-'+'a'*16,'ftv-netflix-'+'b'*16]
        self.roots=[self.make_root(self.directory/i,i) for i in self.ids]
        (self.directory/'profiles.json').write_text(json.dumps({'profiles':[{'id':i,'name':'Viewer '+str(n)} for n,i in enumerate(self.ids)]}))
        self.registry=RecommendationProfiles(self.default,self.directory)
        self.store=EpisodeProgressStore(self.roots[0])
    def tearDown(self):self.temp.cleanup()
    def make_root(self,root,profile):
        root.mkdir();(root/'matches.json').write_text(json.dumps({'profile':profile}))
        (root/'catalogue.json').write_text(json.dumps({SERIES:{'title':'SEAL Team','type':'tv'},SECOND:{'title':'Other'},'flixtor:movie:1':{'title':'Movie'}}))
        return root
    def payload(self,**fields):return dict(action='episode_progress',operation='mark_range',itemId=SERIES,completedSeasons=[1],completedThrough={'season':2,'episode':17},**fields)
    def test_range_round_trip_has_only_explicit_facts(self):
        state=self.store.save(self.payload())
        self.assertEqual(state['completedSeasons'],[1]);self.assertEqual(state['completedThrough'],{'season':2,'episode':17})
        self.assertEqual(state['episodes'],{});self.assertEqual(state['source'],'explicit_user')
        self.assertEqual(set(state),{'completedSeasons','completedThrough','episodes','source','updatedAt'})
        self.assertEqual(EpisodeProgressStore(self.roots[0]).states()[SERIES],state)
        self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode),0o600)
    def test_seasons_normalize_and_omitted_fields_preserve(self):
        payload=self.payload();payload['completedSeasons']=[3,1,1,0]
        self.store.save(payload)
        result=self.store.save(dict(action='episode_progress',operation='mark_range',itemId=SERIES,completedThrough=None))
        self.assertEqual(result['completedSeasons'],[0,1,3]);self.assertIsNone(result['completedThrough'])
    def test_individual_true_false_and_remove_override(self):
        self.store.save(self.payload())
        payload=dict(action='episode_progress',operation='mark_episode',itemId=SERIES,season=2,episode=14,watched=False)
        self.assertEqual(self.store.save(payload)['episodes'],{'2:14':{'watched':False}})
        payload['watched']=True;self.assertEqual(self.store.save(payload)['episodes']['2:14'],{'watched':True})
        payload['watched']=None;result=self.store.save(payload)
        self.assertEqual(result['episodes'],{});self.assertEqual(result['completedThrough']['episode'],17)
    def test_profiles_isolated_and_unknown_profile_rejected(self):
        payload=self.payload();payload['profileId']=self.ids[0]
        with patch('feedback.gorse',side_effect=AssertionError('Gorse must not be called')):self.registry.save(payload)
        self.assertIn(SERIES,self.registry.progress_store(self.ids[0]).states())
        self.assertEqual(self.registry.progress_store(self.ids[1]).states(),{})
        self.assertEqual(self.registry.progress_store().states(),{})
        self.assertEqual(self.registry.store(self.ids[0]).states(),{})
        for ident in ['','../private',self.ids[0]+'/..','ftv-netflix-'+'c'*16,None,[]]:
            with self.subTest(ident=ident),self.assertRaises(ValueError):self.registry.save(dict(payload,profileId=ident))
    def test_read_and_clear_are_title_and_profile_scoped(self):
        self.store.save(self.payload());self.store.save(dict(self.payload(),itemId=SECOND))
        self.assertEqual(len(self.store.save(dict(action='episode_progress',operation='read'))),2)
        self.assertEqual(self.store.save(dict(action='episode_progress',operation='read',itemId=SERIES)),self.store.states()[SERIES])
        self.assertIsNone(self.store.save(dict(action='episode_progress',operation='clear_title',itemId=SERIES)))
        self.assertEqual(set(self.store.states()),{SECOND})
        self.assertIsNone(self.store.save(dict(action='episode_progress',operation='read',itemId=SERIES)))
    def test_invalid_inputs_are_atomic(self):
        self.store.save(self.payload());before=self.store.states()
        invalid=[dict(self.payload(),itemId=i) for i in ['flixtor:movie:1','flixtor:tv:99','../private',[],None]]
        invalid += [dict(self.payload(),completedSeasons=v) for v in [[True],[1.0],['1'],[-1],[1000],list(range(101)),None]]
        invalid += [dict(self.payload(),completedThrough=v) for v in [[],{},dict(season=2,episode=True),dict(season=-1,episode=2),dict(season=2,episode=0),dict(season=2,episode=1,position=2)]]
        invalid += [dict(self.payload(),**{field:1}) for field in ['position','duration','source','updatedAt','profileId']]
        invalid += [dict(self.payload(),operation=[]),dict(self.payload(),operation='unknown'),dict(action='episode_progress',operation='mark_range',itemId=SERIES)]
        invalid += [dict(action='episode_progress',operation='mark_episode',itemId=SERIES,season=2,episode=18,watched=value) for value in [0,1,'yes',[]]]
        for payload in invalid:
            with self.subTest(payload=payload),self.assertRaises(ValueError):self.store.save(payload)
            self.assertEqual(self.store.states(),before)
    def test_progress_survives_recommendation_failure(self):
        self.registry.save(dict(self.payload(),profileId=self.ids[0]))
        def offline(*_):raise OSError('Gorse offline')
        bundle=self.registry.bundle(offline);packs={p['id']:p for p in bundle['profiles']}
        self.assertEqual(packs[self.ids[0]]['episodeProgress'][SERIES]['completedThrough']['episode'],17)
        self.assertEqual(packs[self.ids[1]]['episodeProgress'],{})
        self.assertIn('error',packs[self.ids[0]])
    def test_single_profile_progress_survives_recommendation_failure(self):
        registry=RecommendationProfiles(self.default,self.base/'missing');registry.save(self.payload())
        def offline(*_):raise OSError('Gorse offline')
        self.assertIn(SERIES,registry.bundle(offline)['episodeProgress'])
    def test_cli_defaults_to_dry_run(self):
        root=self.roots[1];args=['episode_progress.py','--data',str(root),'--item',SERIES,'--complete-season','1','--through','2:17']
        with patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()) as output:main()
        self.assertFalse(json.loads(output.getvalue())['applied']);self.assertFalse((root/'episode-progress.sqlite').exists())
        with patch.object(sys,'argv',args+['--apply']),contextlib.redirect_stdout(io.StringIO()) as output:main()
        self.assertTrue(json.loads(output.getvalue())['applied']);self.assertEqual(EpisodeProgressStore(root).states()[SERIES]['completedSeasons'],[1])

if __name__=='__main__':unittest.main()
