"""Private recommendation profile registry over existing bridge endpoints."""
import json,re,threading
from pathlib import Path
from feedback import FeedbackStore

class RecommendationProfiles:
    def __init__(self,default_root,directory=None):
        self.default_root=Path(default_root)
        self.directory=Path(directory) if directory else self.default_root.parent.parent/'netflix/profiles'
        self.lock=threading.RLock();self.stores={}
    def entries(self):
        result=[dict(id='household',name='Household · Amazon unassigned',root=self.default_root)]
        manifest=self.directory/'profiles.json'
        if not manifest.exists():return result
        for p in json.loads(manifest.read_text()).get('profiles',[])[:20]:
            ident=p.get('id','');name=p.get('name','')
            if not re.fullmatch(r'ftv-netflix-[a-f0-9]{16}',ident) or not isinstance(name,str) or not 0<len(name)<=100:continue
            root=self.directory/ident
            if root.is_symlink() or not (root/'matches.json').exists():continue
            if json.loads((root/'matches.json').read_text()).get('profile')!=ident:continue
            result.append(dict(id=ident,name=name,root=root))
        return result
    def store(self,ident=None):
        ident=ident or 'household'
        entry=next((p for p in self.entries() if p['id']==ident),None)
        if entry is None:raise ValueError('Unknown recommendation profile')
        with self.lock:
            if ident not in self.stores:self.stores[ident]=FeedbackStore(entry['root'])
            return self.stores[ident]
    def save(self,payload):
        if not isinstance(payload,dict):raise ValueError('Invalid feedback')
        payload=dict(payload);ident=payload.pop('profileId','household')
        if not isinstance(ident,str):raise ValueError('Invalid profile')
        return self.store(ident).save(payload)
    def bundle(self,recommend):
        entries=self.entries();result=recommend(self.default_root,self.store())
        if len(entries)==1:return result
        packs=[dict(result,id='household',name=entries[0]['name'])]
        for entry in entries[1:]:
            try:pack=recommend(entry['root'],self.store(entry['id']))
            except (OSError,ValueError,KeyError):pack={'engine':'gorse','items':[],'seedCount':0,'error':'Profile recommendations unavailable'}
            packs.append(dict(pack,id=entry['id'],name=entry['name']))
        return dict(result,profiles=packs)
