"""Durable, profile-scoped manual episode facts; never writes FlixTor or Gorse progress.

A timestamp here records when a user assertion was saved, not when viewing occurred.
Complete-season/range assertions contain no invented positions or durations.
"""
import argparse,json,re,sqlite3,threading
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path


def integer(value,minimum,maximum):
    return type(value) is int and minimum<=value<=maximum


def blank():
    return {'completedSeasons':[],'completedThrough':None,'episodes':{}}


class EpisodeProgressStore:
    def __init__(self,root,catalogue_root=None):
        self.root=Path(root);self.catalogue_root=Path(catalogue_root) if catalogue_root else self.root;self.path=self.root/'episode-progress.sqlite';self.lock=threading.RLock()
        profile=json.loads((self.root/'matches.json').read_text()).get('profile')
        if not isinstance(profile,str) or not profile:raise ValueError('Invalid profile')
        self.profile=profile
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS episode_progress (profile TEXT NOT NULL,item TEXT NOT NULL,facts TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(profile,item))')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def validate_item(self,ident):
        items=json.loads((self.catalogue_root/'catalogue.json').read_text())
        if not isinstance(ident,str) or not re.fullmatch(r'flixtor:tv:[0-9]{1,18}',ident) or ident not in items:
            raise ValueError('Choose a series from the current catalogue')
        # The canonical ID is authoritative; reject contradicting media metadata if supplied.
        if items[ident].get('type') not in {None,'tv'}:raise ValueError('Choose a series')
        return ident

    def states(self):
        with self.connect() as db:
            rows=db.execute('SELECT item,facts,updated_at FROM episode_progress WHERE profile=?',(self.profile,)).fetchall()
        return {r['item']:dict(json.loads(r['facts']),source='explicit_user',updatedAt=r['updated_at']) for r in rows}

    def save(self,payload):
        if not isinstance(payload,dict) or payload.get('action')!='episode_progress':raise ValueError('Invalid episode progress action')
        op=payload.get('operation')
        allowed={'read':{'action','operation','itemId'},'mark_range':{'action','operation','itemId','completedSeasons','completedThrough'},'mark_episode':{'action','operation','itemId','season','episode','watched'},'clear_title':{'action','operation','itemId'}}
        if not isinstance(op,str) or op not in allowed or set(payload)-allowed[op]:raise ValueError('Invalid episode progress fields')
        if op=='read' and 'itemId' not in payload:return self.states()
        ident=self.validate_item(payload.get('itemId'))
        if op=='read':return self.states().get(ident)
        if op=='mark_range':
            if not {'completedSeasons','completedThrough'}&set(payload):raise ValueError('Choose a completion range')
            if 'completedSeasons' in payload:
                seasons=payload['completedSeasons']
                if not isinstance(seasons,list) or len(seasons)>100 or any(not integer(n,0,999) for n in seasons):raise ValueError('Invalid completed seasons')
            if 'completedThrough' in payload and payload['completedThrough'] is not None:
                through=payload['completedThrough']
                if not isinstance(through,dict) or set(through)!={'season','episode'} or not integer(through['season'],0,999) or not integer(through['episode'],1,9999):raise ValueError('Invalid completion endpoint')
        if op=='mark_episode':
            if not integer(payload.get('season'),0,999) or not integer(payload.get('episode'),1,9999):raise ValueError('Invalid episode')
            if 'watched' not in payload or payload['watched'] is not None and type(payload['watched']) is not bool:raise ValueError('Choose a watched state')
        at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
        with self.lock:
            with self.connect() as db:
                if op=='clear_title':
                    db.execute('DELETE FROM episode_progress WHERE profile=? AND item=?',(self.profile,ident));return None
                old=db.execute('SELECT facts FROM episode_progress WHERE profile=? AND item=?',(self.profile,ident)).fetchone()
                facts=json.loads(old['facts']) if old else blank()
                if op=='mark_range':
                    if 'completedSeasons' in payload:facts['completedSeasons']=sorted(set(payload['completedSeasons']))
                    if 'completedThrough' in payload:facts['completedThrough']=payload['completedThrough']
                else:
                    key=str(payload['season'])+':'+str(payload['episode'])
                    if payload['watched'] is None:facts['episodes'].pop(key,None)
                    else:facts['episodes'][key]={'watched':payload['watched']}
                encoded=json.dumps(facts,sort_keys=True,separators=(',',':'))
                db.execute('INSERT INTO episode_progress VALUES (?,?,?,?) ON CONFLICT(profile,item) DO UPDATE SET facts=excluded.facts,updated_at=excluded.updated_at',(self.profile,ident,encoded,at))
        return dict(facts,source='explicit_user',updatedAt=at)


def main():
    parser=argparse.ArgumentParser(description='Seed an explicitly authorized, private viewer episode-completion assertion.')
    parser.add_argument('--data',required=True);parser.add_argument('--item',required=True)
    parser.add_argument('--complete-season',action='append',type=int,default=[]);parser.add_argument('--through')
    parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    payload={'action':'episode_progress','operation':'mark_range','itemId':args.item,'completedSeasons':args.complete_season}
    if args.through:
        values=args.through.split(':')
        if len(values)!=2:parser.error('--through must be season:episode')
        try:payload['completedThrough']={'season':int(values[0]),'episode':int(values[1])}
        except ValueError:parser.error('--through must contain integers')
    root=Path(args.data)
    profile=json.loads((root/'matches.json').read_text())['profile']
    if not args.apply:print(json.dumps({'profile':profile,'proposed':payload,'applied':False}));return
    store=EpisodeProgressStore(root);state=store.save(payload)
    print(json.dumps({'profile':profile,'itemId':args.item,'state':state,'applied':True}))


if __name__=='__main__':main()
