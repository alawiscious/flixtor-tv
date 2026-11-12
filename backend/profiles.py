"""Private recommendation profile registry over existing bridge endpoints."""
import json,re,threading,sqlite3
from pathlib import Path
from feedback import FeedbackStore
from episode_progress import EpisodeProgressStore
from recommendation_cache import RecommendationSnapshots

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
    def save(self,payload):
        if not isinstance(payload,dict):raise ValueError('Invalid feedback')
        payload=dict(payload);ident=payload.pop('profileId','household')
        if not isinstance(ident,str) or not ident:raise ValueError('Invalid profile')
        if payload.get('action')=='episode_progress':return self.progress_store(ident).save(payload)
        return self.store(ident).save(payload)
    def bundle(self,recommend):
        entries=self.entries()
        snapshots=self.snapshots.bundle(entries,self.store,recommend)
        packs=[dict(self.with_progress(pack,entry['id']),id=entry['id'],name=entry['name']) for entry,pack in zip(entries,snapshots)]
        result=self.with_progress(snapshots[0],'household')
        return dict(result,profiles=packs) if len(entries)>1 else result
