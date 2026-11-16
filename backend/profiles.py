"""Private recommendation profile registry over existing bridge endpoints."""
import json,re,threading,sqlite3
from pathlib import Path
from feedback import FeedbackStore
from episode_progress import EpisodeProgressStore,blank
from recommendation_cache import RecommendationSnapshots
import watched

class RecommendationProfiles:
    def __init__(self,default_root,directory=None):
        self.default_root=Path(default_root)
        self.directory=Path(directory) if directory else self.default_root.parent.parent/'netflix/profiles'
        self.lock=threading.RLock();self.stores={};self.progress_stores={}
        self.snapshots=RecommendationSnapshots(self.default_root)
    def entries(self):
        result=[dict(id='household',name='Household · Amazon unassigned',root=self.default_root)]
        manifest=self.directory/'profiles.json'
        if not manifest.exists():return result
        try:
            registry=json.loads(manifest.read_text())
            listed=registry.get('profiles',[]) if isinstance(registry,dict) else []
        except (OSError,ValueError):return result
        if not isinstance(listed,list):return result
        for p in listed[:20]:
            if not isinstance(p,dict):continue
            ident=p.get('id','');name=p.get('name','')
            if not isinstance(ident,str) or not re.fullmatch(r'ftv-netflix-[a-f0-9]{16}',ident) or not isinstance(name,str) or not 0<len(name)<=100:continue
            root=self.directory/ident
            if root.is_symlink() or not (root/'matches.json').exists():continue
            try:
                matches=json.loads((root/'matches.json').read_text())
                if not isinstance(matches,dict) or matches.get('profile')!=ident:continue
            except (OSError,ValueError,TypeError):continue
            result.append(dict(id=ident,name=name,root=root))
        return result
    def store(self,ident=None):
        ident=ident or 'household'
        entry=next((p for p in self.entries() if p['id']==ident),None)
        if entry is None:raise ValueError('Unknown recommendation profile')
        with self.lock:
            if ident not in self.stores:self.stores[ident]=FeedbackStore(entry['root'],catalogue_root=self.default_root)
            return self.stores[ident]
    def progress_store(self,ident=None):
        ident=ident or 'household'
        entry=next((p for p in self.entries() if p['id']==ident),None)
        if entry is None:raise ValueError('Unknown recommendation profile')
        with self.lock:
            if ident not in self.progress_stores:self.progress_stores[ident]=EpisodeProgressStore(entry['root'],catalogue_root=self.default_root)
            return self.progress_stores[ident]
    def with_progress(self,pack,ident):
        try:return dict(pack,episodeProgress=self.progress_store(ident).states())
        except (OSError,ValueError,sqlite3.Error):return dict(pack,episodeProgress={},episodeProgressError='Profile episode progress unavailable')
    def with_state(self,pack,ident):
        """Profile facts added fresh to every bundle: the profile's own episode facts, the resolved
        watched map for titles, and the imported layer of episode state (`imported` beside the
        profile's own facts for that series; the app ranks it below them)."""
        pack=self.with_progress(pack,ident)
        try:found=watched.for_store(self.store(ident),self.default_root.parent/'metadata/title-index.sqlite')
        except (OSError,ValueError,sqlite3.Error):return dict(pack,watched={})
        progress=dict(pack['episodeProgress'])
        for series,imported in found['episodes'].items():progress[series]=dict(progress.get(series) or blank(),imported=imported)
        return dict(pack,watched=found['titles'],episodeProgress=progress)
    def save(self,payload):
        if not isinstance(payload,dict):raise ValueError('Invalid feedback')
        payload=dict(payload);ident=payload.pop('profileId','household')
        if not isinstance(ident,str) or not ident:raise ValueError('Invalid profile')
        if payload.get('action')=='episode_progress':return self.progress_store(ident).save(payload)
        return self.store(ident).save(payload)
    def bundle(self,recommend,scope=None):
        """scope=None: the full LAN bundle (household top level + every profile).
        scope=[ids]: a remote device's bundle. Only those profiles are computed or returned; the top
        level is the first allowed profile, never the household unless it is in scope."""
        entries=self.entries()
        if scope is not None:
            entries=[e for e in entries if e['id'] in set(scope)]
            if not entries:raise PermissionError('No recommendation profiles are available to this device')
        snapshots=self.snapshots.bundle(entries,self.store,recommend)
        packs=[dict(self.with_state(pack,entry['id']),id=entry['id'],name=entry['name']) for entry,pack in zip(entries,snapshots)]
        if scope is not None:return dict(packs[0],profiles=packs)
        result=self.with_state(snapshots[0],'household')
        return dict(result,profiles=packs) if len(entries)>1 else result
    def save_scoped(self,payload,scope):
        """Remote feedback: the target profile (default household) must be in the device's scope."""
        ident=payload.get('profileId','household') if isinstance(payload,dict) else None
        if ident not in set(scope):raise PermissionError('This device cannot change that profile')
        return self.save(payload)
