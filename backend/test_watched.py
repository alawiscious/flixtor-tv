import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import watched
from profiles import RecommendationProfiles

NETFLIX='ftv-netflix-'+'a'*16

def index(path,rows,episodes=()):
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE titles(id TEXT PRIMARY KEY,type TEXT,title TEXT,year INTEGER,runtime INTEGER,genres TEXT)')
    db.execute('CREATE TABLE episodes(id TEXT PRIMARY KEY,parent TEXT,season INTEGER,episode INTEGER)')
    db.executemany('INSERT INTO titles VALUES (?,?,?,?,?,?)',rows);db.executemany('INSERT INTO episodes VALUES (?,?,?,?)',episodes);db.commit();db.close()

def movie(ident,title,year='2020',**extra):return dict(id=ident,title=title,year=year,type='movie',genres=[],**extra)
def show(ident,title,year='2020'):return dict(id=ident,title=title,year=year,type='tv',genres=[])
def seed(item,seconds):return dict(item=item,recorded_seconds=seconds,at='2024-01-01T00:00:00Z',source='synthetic')
def view(item,seconds,position=None,episodes=(),metadata_id=None):return dict(item=item,metadata_id=metadata_id,seconds=seconds,position=position,at='2024-01-01T00:00:00Z',episodes=[list(e) for e in episodes])
def netflix(evidence='duration'):return {'watched':True,'source':'netflix','evidence':evidence}

class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.index=Path(self.temp.name)/'title-index.sqlite'
        index(self.index,[('tt1','movie','Finished Film',2020,100,''),('tt2','movie','Half Film',2020,100,''),('tt3','movie','Direct Film',2020,90,''),
                          ('tt4','tvSeries','Long Show',2020,45,''),('tt5','movie','No Runtime',2020,None,''),('tt6','movie','Twin',2020,100,''),('tt7','movie','Twin',2020,100,''),
                          ('tt8','tvSeries','No Usual Length',2020,None,''),('e1','tvEpisode','One',2020,60,''),('e2','tvEpisode','Two',2020,None,''),('e3a','tvEpisode','Three',2020,40,''),('e3b','tvEpisode','Three',2020,90,''),('e9','tvEpisode','Nine',2020,None,'')],
              [('e1','tt4',1,1),('e2','tt4',1,2),('e3a','tt4',1,3),('e3b','tt4',1,3),('e9','tt8',1,1)])
        self.catalogue={'flixtor:movie:1':movie('flixtor:movie:1','Finished Film'),'flixtor:movie:2':movie('flixtor:movie:2','Half Film'),
                        'flixtor:movie:3':movie('flixtor:movie:3','Direct Film'),'flixtor:tv:4':show('flixtor:tv:4','Long Show'),
                        'flixtor:movie:5':movie('flixtor:movie:5','No Runtime'),'flixtor:movie:6':movie('flixtor:movie:6','Twin'),'flixtor:tv:8':show('flixtor:tv:8','No Usual Length')}
        self.features={'flixtor:movie:3':{'source_id':'tt3'}}
    def tearDown(self):self.temp.cleanup()
    def matches(self,viewing=None,seeds=None,profile=NETFLIX):
        out={'profile':profile,'seeds':seeds or []}
        if viewing is not None:out['viewing']=viewing
        return out
    def run_resolve(self,seeds,states=None,profile=NETFLIX):
        return watched.resolve(states or {},self.matches(seeds=seeds,profile=profile),self.catalogue,self.features,self.index)
    def run_viewing(self,viewing,states=None,profile=NETFLIX):
        return watched.resolve(states or {},self.matches(viewing,profile=profile),self.catalogue,self.features,self.index)
    def assess(self,viewing,profile=NETFLIX):
        return watched.assess(self.matches(viewing,profile=profile),self.catalogue,self.features,self.index)

    # Matches files written before viewing facts were recorded: seeds only, play time only.
    def test_legacy_seed_mostly_finished_movie_joins_catalogue_by_title_type_year(self):
        self.assertEqual(self.run_resolve([seed(movie('history:imdb:tt1','Finished Film'),80*60)]),{'flixtor:movie:1':netflix()})
    def test_threshold_is_eighty_percent_of_runtime(self):
        self.assertEqual(self.run_resolve([seed(movie('history:imdb:tt2','Half Film'),79*60)]),{})
        self.assertIn('flixtor:movie:2',self.run_resolve([seed(movie('history:imdb:tt2','Half Film'),80*60)]))
    def test_catalogue_seed_uses_recorded_metadata_id_and_amazon_source(self):
        out=self.run_resolve([seed(self.catalogue['flixtor:movie:3'],80*60)],profile='ftv-amazon-import')
        self.assertEqual(out,{'flixtor:movie:3':{'watched':True,'source':'amazon','evidence':'duration'}})
    def test_series_unknown_runtime_and_missing_seconds_are_never_watched(self):
        seeds=[seed(show('history:imdb:tt4','Long Show'),999999),seed(movie('history:imdb:tt5','No Runtime'),999999),dict(item=movie('history:imdb:tt1','Finished Film'),at='x')]
        self.assertEqual(self.run_resolve(seeds),{})
    def test_ambiguous_title_is_not_joined(self):
        seeds=[seed(movie('history:imdb:tt6','Twin'),6000),seed(movie('history:imdb:tt7','Twin'),6000)]
        self.assertEqual(self.run_resolve(seeds),{})
        self.catalogue['flixtor:movie:7']=movie('flixtor:movie:7','Twin')
        self.assertEqual(self.run_resolve(seeds[:1]),{})
    def test_manual_choice_beats_import_in_both_directions(self):
        seeds=[seed(movie('history:imdb:tt1','Finished Film'),6000)]
        states={'flixtor:movie:1':{'watched':False},'flixtor:movie:2':{'watched':True},'flixtor:movie:5':{'watched':None},'flixtor:movie:999':{'watched':True}}
        out=self.run_resolve(seeds,states)
        self.assertEqual(out,{'flixtor:movie:1':{'watched':False,'source':'manual'},'flixtor:movie:2':{'watched':True,'source':'manual'}})
    def test_missing_index_only_drops_imports(self):
        out=watched.resolve({'flixtor:movie:2':{'watched':True}},{'profile':NETFLIX,'seeds':[seed(movie('history:imdb:tt1','Finished Film'),6000)]},self.catalogue,{},Path(self.temp.name)/'absent.sqlite')
        self.assertEqual(out,{'flixtor:movie:2':{'watched':True,'source':'manual'}})
    def test_sources_stay_in_one_vocabulary(self):
        self.assertEqual({watched.service(NETFLIX),watched.service('ftv-amazon-import'),'manual'},set(watched.SOURCES));self.assertEqual(set(watched.SERVICES),set(watched.SOURCES)-{'manual'})

    # Viewing facts: the furthest position decides when the export states one.
    def test_position_reached_decides_and_play_time_cannot_overrule_it(self):
        film=movie('history:imdb:tt1','Finished Film')
        self.assertEqual(self.run_viewing([view(film,10*60,position=80*60)]),{'flixtor:movie:1':netflix('position')},'reached the end with little recorded play time')
        self.assertEqual(self.run_viewing([view(film,200*60,position=79*60)]),{},'the first part played twice is not finishing')
    def test_play_time_is_used_only_when_no_position_is_stated(self):
        film=movie('history:imdb:tt1','Finished Film')
        for position in (None,0):self.assertEqual(self.run_viewing([view(film,80*60,position=position)]),{'flixtor:movie:1':netflix('duration')})
        self.assertEqual(self.run_viewing([view(film,79*60)]),{})
    def test_recorded_metadata_id_is_used_for_a_catalogue_item(self):
        self.assertEqual(self.run_viewing([view(self.catalogue['flixtor:movie:2'],0,position=90*60,metadata_id='tt2')]),{'flixtor:movie:2':netflix('position')})
        self.assertEqual(self.run_viewing([view(self.catalogue['flixtor:movie:2'],0,position=90*60)]),{},'no id on record means no length, so nothing is decided')
    def test_viewing_replaces_seeds_when_present(self):
        out=watched.resolve({},self.matches([],seeds=[seed(movie('history:imdb:tt1','Finished Film'),6000)]),self.catalogue,self.features,self.index)
        self.assertEqual(out,{})

    def test_episode_is_measured_against_its_own_length_then_the_series_usual_length(self):
        found=self.assess([view(show('history:imdb:tt4','Long Show'),0,episodes=[(1,1,3000,48*60),(1,1+1,2000,36*60),(1,3,0,36*60),(2,9,36*60,None),(3,1,60,35*60)])])
        # 1:1 own length 60 min -> 48 reached is exactly 80%. 1:2 has no own length -> usual 45 min. 1:3 has two conflicting
        # lengths -> usual. 2:9 is not listed -> usual, by play time. 3:1 reached 35 of 45 min -> not finished.
        self.assertEqual(found['episodes'],{'flixtor:tv:4':{(1,1):'position',(1,2):'position',(1,3):'position',(2,9):'duration'}})
        self.assertEqual(found['report']['episodes'],5);self.assertEqual(found['report']['episodes measured against episode length'],1)
        self.assertEqual(found['report']['episodes measured against series length'],3);self.assertEqual(found['report']['episodes not finished'],1)
        self.assertEqual(watched.imported_episodes(found),{'flixtor:tv:4':{'netflix':{'1':[1,2,3],'2':[9]}}})
        self.assertEqual(found['titles'],{},'finished episodes never mark the series itself')
    def test_episode_own_length_wins_over_the_usual_length(self):
        found=self.assess([view(show('history:imdb:tt4','Long Show'),0,episodes=[(1,1,0,40*60)])])
        self.assertEqual(found['episodes'],{},'40 of 60 minutes, although it passes the usual 45')
    def test_episodes_without_any_length_or_catalogue_series_are_counted_not_decided(self):
        found=self.assess([view(show('history:imdb:tt8','No Usual Length'),0,episodes=[(1,1,9999,9999)]),view(show('history:imdb:tt99','Elsewhere'),0,episodes=[(1,1,9999,9999),(1,2,9999,9999)]),
                           view(show('history:imdb:tt4','Yearless','') ,0,episodes=[(1,1,9999,9999)])],profile='ftv-amazon-import')
        self.assertEqual(found['episodes'],{});self.assertEqual(found['named_episodes'],{});self.assertEqual(found['report']['episodes length unknown'],3,'one catalogue series and one named series, neither with a length on record')
        self.assertEqual(found['report']['episodes of series not in catalogue'],3);self.assertEqual(found['report']['episodes of series with no usable name'],1);self.assertEqual(found['source'],'amazon')
    def test_malformed_viewing_rows_are_ignored(self):
        rows=[None,{'item':None},{'item':{'type':'short'}},dict(item=show('history:imdb:tt4','Long Show'),seconds='x',episodes=[[1],[0,1,5,5],['1',1,5,5],[1,2,True,9999]])]
        found=self.assess(rows);self.assertEqual(found['episodes'],{'flixtor:tv:4':{(1,2):'position'}});self.assertEqual(found['report']['episodes'],1)
    def test_report_counts_every_film_once(self):
        report=self.assess([view(movie('history:imdb:tt1','Finished Film'),0,90*60),view(movie('history:imdb:tt2','Half Film'),0,10*60),view(movie('history:imdb:tt5','No Runtime'),9999,9999),view(movie('history:imdb:tt3','Unlisted Film'),90*60)])['report']
        self.assertEqual((report['films'],report['films finished by position'],report['films not finished'],report['films length unknown'],report['films finished by duration'],report['films finished, not in catalogue']),(4,1,1,1,1,1))

    # Finished titles the catalogue does not hold yet are published by name.
    NAME_CASES=[(('movie','Am\u00e9lie','2001'),'movie|amelie|2001'),(('tv','Se7en: The  Beginning!',2019),'tv|se7enthebeginning|2019'),(('movie','Stra\u00dfe','1999'),'movie|strae|1999'),
                (('movie','Film','2020 \u00b7 1h 30m'),'movie|film|2020'),(('movie','Film',''),None),(('movie','!!!','2020'),None),(('short','Film','2020'),None),(('movie','Film','0000'),None)]
    def test_name_key_cases_shared_with_the_app(self):
        for (kind,title,year),expected in self.NAME_CASES:self.assertEqual(watched.name_key(dict(type=kind,title=title,year=year)),expected,(kind,title,year))
    def test_finished_titles_outside_the_catalogue_are_offered_by_name(self):
        self.index.unlink();index(self.index,[('tt20','movie','Unlisted Film',2019,100,''),('tt21','tvSeries','Unlisted Show',2018,30,''),('tt22','movie','Unfinished Film',2019,100,''),('tt1','movie','Finished Film',2020,100,'')])
        viewing=[view(movie('history:imdb:tt20','Unlisted Film','2019'),0,90*60),view(show('history:imdb:tt21','Unlisted Show','2018'),0,episodes=[(1,2,0,29*60),(1,1,1800,None),(2,1,60,5*60)]),
                 view(movie('history:imdb:tt22','Unfinished Film','2019'),0,10*60),view(movie('history:imdb:tt1','Finished Film'),0,90*60)]
        found=self.assess(viewing)
        self.assertEqual(found['named_titles'],{'movie|unlistedfilm|2019':'position'});self.assertEqual(found['named_episodes'],{'tv|unlistedshow|2018':{(1,1):'duration',(1,2):'position'}})
        self.assertEqual(found['titles'],{'flixtor:movie:1':'position'},'a title the catalogue holds stays in the id map and is not offered by name as well')
        self.assertEqual(watched.named(found),({'netflix':['movie|unlistedfilm|2019']},{'netflix':{'tv|unlistedshow|2018':{'1':[1,2]}}}))
        self.assertEqual((found['report']['films finished, offered by name'],found['report']['episodes finished, offered by name']),(1,2))
        # Once the catalogue learns the title, it moves to the id map and leaves the name map.
        self.catalogue['flixtor:movie:20']=movie('flixtor:movie:20','Unlisted Film','2019');self.catalogue['flixtor:tv:21']=show('flixtor:tv:21','Unlisted Show','2018')
        found=self.assess(viewing);self.assertEqual(found['named_titles'],{});self.assertEqual(found['named_episodes'],{})
        self.assertEqual(found['titles']['flixtor:movie:20'],'position');self.assertEqual(set(found['episodes']['flixtor:tv:21']),{(1,1),(1,2)})
    def test_a_name_is_offered_only_when_unambiguous(self):
        self.index.unlink();index(self.index,[('tt6','movie','Twin',2020,100,''),('tt7','movie','Twin',2020,100,''),('tt30','movie','Remade',2020,100,''),('tt31','movie','Remade',2020,100,''),('tt32','movie','No Year',None,100,'')])
        twins=[view(movie('history:imdb:tt30','Remade'),0,6000),view(movie('history:imdb:tt31','Remade'),0,6000)]
        self.assertEqual(self.assess(twins)['named_titles'],{},'two viewed titles of one name')
        self.assertEqual(self.assess(twins[:1])['named_titles'],{'movie|remade|2020':'position'})
        self.assertEqual(self.assess([view(movie('history:imdb:tt32','No Year',''),0,6000)])['named_titles'],{},'no year, no name')
        self.catalogue['flixtor:movie:7']=movie('flixtor:movie:7','Twin')
        found=self.assess([view(movie('history:imdb:tt6','Twin'),0,6000)]);self.assertEqual((found['titles'],found['named_titles']),({},{}),'two catalogue titles of that name: neither map answers')
        self.assertEqual(watched.named(found),({},{}))

class BundleTests(unittest.TestCase):
    def test_bundle_carries_each_profiles_own_watched_map_and_imported_episodes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);default=root/'amazon/personalized';directory=root/'netflix/profiles';default.mkdir(parents=True);directory.mkdir(parents=True);(root/'amazon/metadata').mkdir()
            index(root/'amazon/metadata/title-index.sqlite',[('tt1','movie','Finished Film',2020,100,''),('tt4','tvSeries','Long Show',2020,45,''),('tt20','movie','Unlisted Film',2019,100,'')])
            catalogue={'flixtor:movie:1':movie('flixtor:movie:1','Finished Film'),'flixtor:movie:2':movie('flixtor:movie:2','Other Film'),'flixtor:tv:4':show('flixtor:tv:4','Long Show'),'flixtor:tv:5':show('flixtor:tv:5','Own Show')}
            (default/'catalogue.json').write_text(json.dumps(catalogue));(default/'matches.json').write_text(json.dumps({'profile':'ftv-amazon-import','seeds':[]}))
            viewing=[view(movie('history:imdb:tt1','Finished Film'),6000,95*60),view(catalogue['flixtor:tv:4'],0,episodes=[(1,1,2700,2700),(1,2,300,300)],metadata_id='tt4'),view(movie('history:imdb:tt20','Unlisted Film','2019'),0,95*60)]
            (directory/NETFLIX).mkdir();(directory/NETFLIX/'matches.json').write_text(json.dumps({'profile':NETFLIX,'seeds':[],'viewing':viewing}))
            (directory/'profiles.json').write_text(json.dumps({'profiles':[{'id':NETFLIX,'name':'Example'}]}))
            registry=RecommendationProfiles(default,directory)
            with patch('feedback.gorse',return_value={}):registry.save({'profileId':'household','itemId':'flixtor:movie:2','watched':True})
            registry.save({'profileId':NETFLIX,'action':'episode_progress','operation':'mark_episode','itemId':'flixtor:tv:4','season':1,'episode':1,'watched':False})
            registry.save({'profileId':NETFLIX,'action':'episode_progress','operation':'mark_episode','itemId':'flixtor:tv:5','season':1,'episode':1,'watched':True})
            result=registry.bundle(lambda *_:{'engine':'gorse','items':[]})
            self.assertEqual(result['watched'],{'flixtor:movie:2':{'watched':True,'source':'manual'}});self.assertEqual(result['episodeProgress'],{})
            packs={p['id']:p for p in result['profiles']}
            self.assertEqual(packs['household']['watched'],result['watched'])
            self.assertEqual(packs[NETFLIX]['watched'],{'flixtor:movie:1':netflix('position')})
            self.assertEqual((packs[NETFLIX]['watchedNames'],packs[NETFLIX]['importedEpisodeNames'],result['watchedNames'],result['importedEpisodeNames']),({'netflix':['movie|unlistedfilm|2019']},{},{},{}))
            progress=packs[NETFLIX]['episodeProgress']
            # The import layer sits beside the profile's own facts for the series; it never rewrites them.
            self.assertEqual(progress['flixtor:tv:4']['imported'],{'netflix':{'1':[1]}});self.assertEqual(progress['flixtor:tv:4']['episodes'],{'1:1':{'watched':False}})
            self.assertEqual(progress['flixtor:tv:4']['source'],'explicit_user');self.assertNotIn('imported',progress['flixtor:tv:5'])
            self.assertEqual(registry.progress_store(NETFLIX).states()['flixtor:tv:4'].get('imported'),None,'imports are never written into the profile\'s own store')
            scoped=registry.bundle(lambda *_:{'engine':'gorse','items':[]},scope=[NETFLIX])
            self.assertEqual(scoped['watched'],packs[NETFLIX]['watched']);self.assertEqual(scoped['episodeProgress'],progress);self.assertEqual([p['id'] for p in scoped['profiles']],[NETFLIX])
    def test_assessment_is_redone_only_when_an_input_file_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);default=root/'amazon/personalized';default.mkdir(parents=True);(root/'amazon/metadata').mkdir()
            index(root/'amazon/metadata/title-index.sqlite',[('tt1','movie','Finished Film',2020,100,'')])
            catalogue={'flixtor:movie:1':movie('flixtor:movie:1','Finished Film'),'flixtor:movie:2':movie('flixtor:movie:2','Other Film')};(default/'catalogue.json').write_text(json.dumps(catalogue))
            write=lambda position:(default/'matches.json').write_text(json.dumps({'profile':'ftv-amazon-import','seeds':[],'viewing':[view(movie('history:imdb:tt1','Finished Film'),0,position)]}))
            write(95*60);registry=RecommendationProfiles(default,root/'none');bundle=lambda:registry.bundle(lambda *_:{'engine':'gorse','items':[]})['watched']
            with patch('watched.assess',wraps=watched.assess) as assess:
                self.assertEqual(set(bundle()),{'flixtor:movie:1'});self.assertEqual(set(bundle()),{'flixtor:movie:1'});self.assertEqual(assess.call_count,1)
                # The profile's own choice is never kept: it shows at once, without a new assessment.
                with patch('feedback.gorse',return_value={}):registry.save({'profileId':'household','itemId':'flixtor:movie:2','watched':True})
                self.assertEqual(set(bundle()),{'flixtor:movie:1','flixtor:movie:2'});self.assertEqual(assess.call_count,1)
                write(1000*60+1);self.assertEqual(set(bundle()),{'flixtor:movie:1','flixtor:movie:2'});self.assertEqual(assess.call_count,2)
                write(10*60);self.assertEqual(set(bundle()),{'flixtor:movie:2'},'a changed matches file is assessed again');self.assertEqual(assess.call_count,3)
    def test_series_with_imports_only_gets_blank_own_facts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);default=root/'amazon/personalized';default.mkdir(parents=True);(root/'amazon/metadata').mkdir()
            index(root/'amazon/metadata/title-index.sqlite',[('tt4','tvSeries','Long Show',2020,45,'')])
            catalogue={'flixtor:tv:4':show('flixtor:tv:4','Long Show')};(default/'catalogue.json').write_text(json.dumps(catalogue))
            (default/'matches.json').write_text(json.dumps({'profile':'ftv-amazon-import','seeds':[],'viewing':[view(catalogue['flixtor:tv:4'],0,episodes=[(2,3,2700,None)],metadata_id='tt4')]}))
            result=RecommendationProfiles(default,root/'none').bundle(lambda *_:{'engine':'gorse','items':[]})
            self.assertEqual(result['episodeProgress'],{'flixtor:tv:4':{'completedSeasons':[],'completedThrough':None,'episodes':{},'imported':{'amazon':{'2':[3]}}}})

if __name__=='__main__':unittest.main()
