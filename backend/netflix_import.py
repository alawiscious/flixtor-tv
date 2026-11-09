#!/usr/bin/env python3
"""Private, profile-separated Netflix export import. No account/billing/location import.
Only exact, unambiguous catalogue/metadata identities become recommendation signals.
Netflix playback is evidence of viewing, never inferred liking or completion.
"""
import argparse,collections,csv,hashlib,io,json,re,sqlite3,zipfile,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from history_index import norm
from enrich_history import genre_tags
from recommendation_features import vector
from personalize import call

SEASON=re.compile(r'^(.*?):\s*(?:Season\s+\d+|Limited Series|Series\s+\d+|Part\s+\d+|Volume\s+\d+|Book\s+\d+|Collection\s+\d+|Temporada\s+\d+|Saison\s+\d+|Staffel\s+\d+)(?:\s*:|$)',re.I)
OWNER='Netflix export import v1'
def profile_id(name):return 'ftv-netflix-'+hashlib.sha256(name.encode()).hexdigest()[:16]
def seconds(value):
    try:
        parts=str(value).split(':')
        if len(parts)!=3:return None
        h,m,s=map(int,parts)
        return h*3600+m*60+s if h>=0 and 0<=m<60 and 0<=s<60 else None
    except (ValueError,TypeError):return None
def timestamp(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    except (ValueError,TypeError):return None
def rating(kind,star,thumb):
    if kind=='thumb':return {'1':'dislike','2':'like','3':'like','0':'clear'}.get(thumb,'unknown')
    if kind=='star':return 'like' if star in {'4','5'} else 'dislike' if star in {'1','2'} else 'dislike' if star=='-1' else 'unwatched' if star=='-2' else 'clear' if star in {'0','3'} else 'unknown'
    return 'unknown'
def rows(archive,suffix):
    found=[x for x in archive.infolist() if x.filename.endswith('/'+suffix)]
    if len(found)!=1:raise ValueError('Expected one '+suffix)
    info=found[0]
    if info.file_size>100_000_000:raise ValueError('CSV exceeds import limit')
    return csv.DictReader(io.StringIO(archive.read(info).decode('utf-8-sig')))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(path)

def stage(archive_path,db_path):
    db_path=Path(db_path);db_path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=sqlite3.connect(db_path);db.row_factory=sqlite3.Row
    db.executescript('''CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,name TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,profile TEXT,kind TEXT,title TEXT,at TEXT,seconds INTEGER,supplemental TEXT,signal TEXT,bookmark TEXT,latest_bookmark TEXT);
    CREATE TABLE IF NOT EXISTS imports(sha256 TEXT PRIMARY KEY,at TEXT);''')
    digest=hashlib.sha256(Path(archive_path).read_bytes()).hexdigest();unknown=0
    with zipfile.ZipFile(archive_path) as z, db:
        for r in rows(z,'PROFILES/Profiles.csv'):
            name=r['Profile Name'].strip()
            if not name:raise ValueError('Empty profile name')
            db.execute('INSERT OR IGNORE INTO profiles VALUES (?,?)',(profile_id(name),name))
        known={r['name']:r['id'] for r in db.execute('SELECT * FROM profiles')}
        for kind,suffix in [('view','ViewingActivity.csv'),('rating','Ratings.csv'),('list','MyList.csv')]:
            for r in rows(z,'CONTENT_INTERACTION/'+suffix):
                name=r['Profile Name'].strip()
                if name not in known:unknown+=1;continue
                title=r.get('Title',r.get('Title Name','')).strip()
                at=timestamp(r.get('Start Time') or r.get('Event Utc Ts') or r.get('Utc Title Add Date'))
                sec=seconds(r.get('Duration')) if kind=='view' else 0
                signal=rating(r.get('Rating Type'),r.get('Star Value'),r.get('Thumbs Value')) if kind=='rating' else ''
                values=[known[name],kind,title,at,sec,r.get('Supplemental Video Type',''),signal,r.get('Bookmark',''),r.get('Latest Bookmark','')]
                ident=hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?)',[ident]+values)
        db.execute('INSERT OR IGNORE INTO imports VALUES (?,?)',(digest,datetime.now(timezone.utc).isoformat()))
    db_path.chmod(0o600);return db,unknown

class Resolver:
    def __init__(self,items,index):
        self.items=items;self.metadata=collections.defaultdict(list);self.catalogue=collections.defaultdict(list);self.cache={}
        for i in items.values():self.catalogue[norm(i['title'])].append(i)
        conn=sqlite3.connect('file:'+str(Path(index).resolve())+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
        for r in conn.execute("SELECT * FROM titles WHERE type IN ('movie','tvMovie','tvSeries','tvMiniSeries')"):
            r=dict(r);self.metadata[norm(r['title'])].append(r)
        conn.close()
    def resolve(self,title,at):
        season=SEASON.match(title);base=season[1].strip() if season else title
        key=(base,bool(season),at[:4]);
        if key in self.cache:return self.cache[key]
        year=re.search(r'\((19\d{2}|20\d{2})\)$',base)
        if year:base=base[:year.start()].strip()
        typ='tv' if season else None;latest=int(at[:4]);wanted=int(year[1]) if year else None
        candidates=[m for m in self.metadata.get(norm(base),[]) if (not typ or m['type'] in {'tvSeries','tvMiniSeries'}) and (not wanted or m['year']==wanted) and (not m['year'] or m['year']<=latest)]
        # Multiple remakes/type collisions remain unresolved even if only one is playable.
        if len(candidates)>1:result=None
        elif candidates:
            m=candidates[0];kind='tv' if m['type'] in {'tvSeries','tvMiniSeries'} else 'movie'
            canon=[i for i in self.catalogue.get(norm(m['title']),[]) if i['type']==kind and i['year']==str(m['year'])]
            result=dict(canon[0]) if len(canon)==1 else dict(id='history:imdb:'+m['id'],title=m['title'],year=str(m['year'] or ''),type=kind,genres=genre_tags(m['genres'].split(',')),metadata_id=m['id'])
        else:
            canon=[i for i in self.catalogue.get(norm(base),[]) if (not typ or i['type']==typ) and (not wanted or i['year']==str(wanted)) and (not i['year'] or int(i['year'])<=latest)]
            result=dict(canon[0]) if len(canon)==1 else None
        if result:result['genres']=genre_tags(result['genres']);result['meta']=', '.join(result['genres'])
        self.cache[key]=result;return result

def prepare(db,items,resolver,out,base_features=None):
    profiles=[];all_items=dict(items)
    for p in db.execute('SELECT * FROM profiles ORDER BY name'):
        counts=collections.Counter();groups={};unresolved=[]
        events=db.execute('SELECT * FROM events WHERE profile=? ORDER BY at,id',(p['id'],)).fetchall()
        for row in events:
            r=dict(row);counts[r['kind']+'_rows']+=1
            if r['kind']=='view' and r['supplemental']:
                counts['supplemental_excluded']+=1;continue
            if not r['at'] or not r['title'] or r['kind']=='view' and (r['seconds'] is None or r['seconds']<120):
                counts['short_or_invalid_excluded']+=1;continue
            if r['kind']=='rating' and r['signal']=='unknown':counts['uninterpreted_ratings']+=1;continue
            item=resolver.resolve(r['title'],r['at'])
            if not item:
                unresolved.append({'event':r['id'],'title':r['title'],'kind':r['kind']});continue
            counts['resolved_'+r['kind']+'_rows']+=1;all_items[item['id']]=item
            group=groups.setdefault(item['id'],{'item':item,'seconds':0,'seen_at':None,'list_at':None,'preference':None,'preference_at':None})
            if r['kind']=='view':group['seconds']+=r['seconds'];group['seen_at']=max(group['seen_at'] or '',r['at'])
            elif r['kind']=='list':group['list_at']=max(group['list_at'] or '',r['at'])
            elif group['preference_at'] is None or r['at']>=group['preference_at']:group['preference']=r['signal'];group['preference_at']=r['at']
        seeds=[];seen=[];feedback=[];negatives=[]
        for ident,g in groups.items():
            unseen=g['preference']=='unwatched' and (not g['seen_at'] or g['preference_at']>=g['seen_at'])
            if unseen:feedback.append(dict(FeedbackType='recommend_unwatched',UserId=p['id'],ItemId=ident,Value=1,Timestamp=g['preference_at'],Comment=OWNER))
            if g['seen_at'] and not unseen:
                seen.append(ident);feedback.append(dict(FeedbackType='watched',UserId=p['id'],ItemId=ident,Value=1,Timestamp=g['seen_at'],Comment=OWNER))
            if g['preference']=='dislike':
                negatives.append(ident);seen.append(ident);feedback.append(dict(FeedbackType='recommend_dislike',UserId=p['id'],ItemId=ident,Value=1,Timestamp=g['preference_at'],Comment=OWNER));continue
            if not g['item']['genres']:continue
            like=g['preference']=='like';interest=(g['seconds']>=1200 and not unseen) or g['list_at']
            if not like and not interest:continue
            at=g['preference_at'] if like else g['seen_at'] or g['list_at']
            source='explicit Netflix rating' if like else 'historical Netflix watchlist interest' if g['list_at'] and not g['seconds'] else 'recorded Netflix viewing'
            seed=dict(item=g['item'],at=at,source=source,feedback_type='like' if like else 'import_interest',recorded_seconds=g['seconds'])
            seeds.append(seed);feedback.append(dict(FeedbackType=seed['feedback_type'],UserId=p['id'],ItemId=ident,Value=1,Timestamp=at,Comment=OWNER))
        root=Path(out)/p['id'];write(root/'catalogue.json',items)
        write(root/'matches.json',dict(profile=p['id'],profile_name=p['name'],scope='Netflix · '+p['name'],seeds=seeds,seen=sorted(set(seen)),review=[],negative_ids=negatives))
        write(root/'gorse-feedback.json',feedback);write(root/'unresolved.json',unresolved)
        features={i['id']:(base_features or {}).get(i['id'],dict(metadata_vector=vector(i),creators=[])) for i in list(items.values())+[s['item'] for s in seeds]};write(root/'recommendation-features.json',features)
        report=dict(id=p['id'],name=p['name'],**counts,interest_titles=len(seeds),seen_titles=len(set(seen)),disliked_titles=len(negatives),unresolved_rows=len(unresolved),feedback_records=len(feedback))
        profiles.append(report);write(root/'import-report.json',report)
    write(Path(out)/'profiles.json',{'schema':1,'profiles':profiles,'amazon':'Kept separate and unassigned; no viewer identity available'})
    return profiles,all_items

def apply(profiles,all_items,out,items):
    # Keep existing shared catalogue metadata intact; upload only absent history items.
    needed={s['item']['id'] for p in profiles for s in json.loads((Path(out)/p['id']/'matches.json').read_text())['seeds']}
    for p in profiles:
        root=Path(out)/p['id'];needed.update(r['ItemId'] for r in json.loads((root/'gorse-feedback.json').read_text()))
    for ident in sorted(needed):
        if ident in items:continue
        try:call('/api/item/'+quote(ident,safe=''));continue
        except urllib.error.HTTPError as error:
            if error.code!=404:raise
        i=all_items[ident];call('/api/items',[dict(ItemId=ident,IsHidden=True,Categories=['history-only',i['type']],Labels=dict(genres=i['genres'],title=i['title'],year=i['year'],metadata_vector=vector(i),creators=[]),Comment=i['title'])],'POST')
    for p in profiles:
        root=Path(out)/p['id'];call('/api/users',[dict(UserId=p['id'],Labels={'source':'netflix','display_name':p['name']},Comment='Separate Netflix viewer; not a FlixTor login')],'POST')
        desired=json.loads((root/'gorse-feedback.json').read_text());keys={(r['FeedbackType'],r['ItemId']) for r in desired}
        for old in call('/api/user/'+quote(p['id'],safe='')+'/feedback'):
            if old.get('Comment')==OWNER and (old['FeedbackType'],old['ItemId']) not in keys:call('/api/feedback/'+quote(old['FeedbackType'],safe='')+'/'+quote(p['id'],safe='')+'/'+quote(old['ItemId'],safe=''),method='DELETE')
        for offset in range(0,len(desired),500):call('/api/feedback',desired[offset:offset+500],'PUT')
        actual=call('/api/user/'+quote(p['id'],safe='')+'/feedback');actual_keys={(r['FeedbackType'],r['ItemId']) for r in actual}
        if not keys<=actual_keys:raise RuntimeError('Gorse feedback verification failed')
        write(root/'gorse-apply-report.json',{'verified_feedback':len(keys),'profile':p['id']})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',required=True);parser.add_argument('--db',required=True);parser.add_argument('--catalogue',required=True);parser.add_argument('--metadata',required=True);parser.add_argument('--out',required=True);parser.add_argument('--apply',action='store_true');a=parser.parse_args()
    db,unknown=stage(a.archive,a.db);items=json.loads(Path(a.catalogue).read_text());features=Path(a.catalogue).parent/'recommendation-features.json';profiles,all_items=prepare(db,items,Resolver(items,a.metadata),a.out,json.loads(features.read_text()) if features.exists() else {});db.close()
    if a.apply:apply(profiles,all_items,a.out,items)
    print(json.dumps({'profiles':profiles,'unknown_profile_rows':unknown,'applied':a.apply},indent=2))
if __name__=='__main__':main()
