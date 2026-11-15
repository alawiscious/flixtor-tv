"""Durable, profile-scoped recommendation feedback. Raw history never leaves the Mac.

Two independent concepts per profile and title:
- preference: interest before watching ('like' = good recommendation, 'dislike' = not for me, 'clear')
- rating: opinion after watching ('love' | 'like' | 'dislike' | 'hate' | None). A rating is a fact that
  the title was seen, so saving one also sets watched=True (resolved here, nowhere else).
"""
import json,sqlite3,threading,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import quote

RATINGS=('love','like','dislike','hate')
TYPES=('recommend_like','recommend_dislike','recommend_watched','recommend_unwatched')+tuple('rating_'+r for r in RATINGS)

def gorse(path,payload=None,method=None):
    req=urllib.request.Request('http://127.0.0.1:8088'+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)

class FeedbackStore:
    def __init__(self,root,catalogue_root=None):
        self.root=Path(root);self.catalogue_root=Path(catalogue_root) if catalogue_root else self.root;self.path=self.root/'user-feedback.sqlite';self.lock=threading.RLock()
        with self.connect() as db:
            db.execute('create table if not exists feedback(profile text,item text,preference text not null default "clear",watched integer,at text not null,synced integer not null default 0,primary key(profile,item))')
            if 'rating' not in {r['name'] for r in db.execute('pragma table_info(feedback)')}:db.execute('alter table feedback add column rating text')
        self.path.chmod(0o600)
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def profile(self):return json.loads((self.root/'matches.json').read_text())['profile']
    def states(self):
        with self.connect() as db:rows=db.execute('select * from feedback where profile=?',(self.profile(),)).fetchall()
        return {r['item']:dict(preference=r['preference'],watched=None if r['watched'] is None else bool(r['watched']),rating=r['rating'],syncPending=not bool(r['synced']),at=r['at']) for r in rows}
    def save(self,payload):
        if not isinstance(payload,dict) or set(payload)-{'itemId','preference','watched','rating'}:raise ValueError('Invalid feedback fields')
        ident=payload.get('itemId');items=json.loads((self.catalogue_root/'catalogue.json').read_text())
        if not isinstance(ident,str) or ident not in items:raise ValueError('Choose a title from the current catalogue')
        if len(payload)==1:raise ValueError('Choose recommendation or watch feedback')
        preference=payload.get('preference','clear')
        if 'preference' in payload and preference not in {'like','dislike','clear'}:raise ValueError('Invalid preference')
        if 'watched' in payload and payload['watched'] is not None and type(payload['watched']) is not bool:raise ValueError('Invalid watch state')
        if 'rating' in payload and payload['rating'] is not None and payload['rating'] not in RATINGS:raise ValueError('Invalid rating')
        profile=self.profile();at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
        with self.lock:
            with self.connect() as db:
                old=db.execute('select * from feedback where profile=? and item=?',(profile,ident)).fetchone()
                preference=payload['preference'] if 'preference' in payload else old['preference'] if old else 'clear'
                watched=payload['watched'] if 'watched' in payload else old['watched'] if old else None
                rating=payload['rating'] if 'rating' in payload else old['rating'] if old else None
                if rating is not None:watched=True # a rating means the title was seen
                db.execute('insert into feedback(profile,item,preference,watched,at,synced,rating) values (?,?,?,?,?,0,?) on conflict(profile,item) do update set preference=excluded.preference,watched=excluded.watched,rating=excluded.rating,at=excluded.at,synced=0',(profile,ident,preference,watched,at,rating))
            self.sync(ident)
        return self.states()[ident]
    def sync(self,ident=None):
        with self.lock:
            profile=self.profile()
            with self.connect() as db:
                rows=db.execute('select * from feedback where profile=? and synced=0'+(' and item=?' if ident else '')+' limit 12',(profile,ident) if ident else (profile,)).fetchall()
            for row in rows:
                try:
                    desired={}
                    if row['preference']!='clear':desired['recommend_'+row['preference']]=1
                    if row['watched'] is not None:desired['recommend_watched' if row['watched'] else 'recommend_unwatched']=1
                    if row['rating']:desired['rating_'+row['rating']]=1
                    for kind in TYPES:
                        if kind not in desired:
                            try:gorse('/api/feedback/'+quote(kind,safe='')+'/'+quote(profile,safe='')+'/'+quote(row['item'],safe=''),method='DELETE')
                            except urllib.error.HTTPError as error:
                                if error.code!=404:raise
                    if desired:gorse('/api/feedback',[{'FeedbackType':kind,'UserId':profile,'ItemId':row['item'],'Value':1,'Timestamp':row['at'],'Comment':'User recommendation feedback; not inferred completion'} for kind in desired],'PUT')
                    with self.connect() as db:db.execute('update feedback set synced=1 where profile=? and item=? and at=?',(profile,row['item'],row['at']))
                except (OSError,ValueError):break # Keep the outbox; retry when Gorse is reachable.
