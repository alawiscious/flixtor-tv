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

SEASON_NUMBER=re.compile(r'(?:Season|Series|Temporada|Saison|Staffel)\s+(\d+)',re.I)
SERIES={'tvSeries','tvMiniSeries'}
# The export states the episode number itself: "Show: Season 2: Episode Name (Episode 3)".
EPISODE_TAG=re.compile(r'\s*\((?:Episode|Chapter|Episodio|Capítulo|Folge|Épisode)\s+(\d+)\)\s*$',re.I)
METHODS=('unique title','unique movie title','episode names among same-named titles','series before an episode name','catalogue title')

def splits(title):
    """Ways a recorded title can name a show, most specific first:
    (base, episode name or None, explicit, season or None, episode number or None).
    explicit: the export itself marks this as an episode (season marker or episode tag), so base is a series."""
    tag=EPISODE_TAG.search(title);number=int(tag[1]) if tag else None;body=title[:tag.start()] if tag else title
    season=SEASON.match(body)
    if season:
        rest=body[season.end():].strip(' :');marker=body[len(season[1]):season.end()];found=SEASON_NUMBER.search(marker)
        # A limited series is one season by definition; other markers (Part, Volume) are not season numbers.
        return [(season[1].strip(),rest or None,True,int(found[1]) if found else 1 if re.search('limited series',marker,re.I) else None,number)]
    segments=[x.strip() for x in body.split(':')];out=[] if tag and len(segments)>1 else [(body,None,False,None,None)]
    for n in range(len(segments)-1,0,-1):
        base=': '.join(segments[:n]);episode=': '.join(segments[n:])
        if base and episode:out.append((base,episode,bool(tag),None,number))
    return out or [(body,None,False,None,None)]

class Resolver:
    """Title -> one catalogue/IMDb identity, or None. Never guesses between same-named titles:
    a tie is broken only by facts in the export itself (the episode names watched under that name)."""
    def __init__(self,items,index):
        self.items=items;self.metadata=collections.defaultdict(list);self.catalogue=collections.defaultdict(list);self.cache={}
        self.evidence=collections.defaultdict(set);self.methods={};self.imdb={};self.listed={};self.used={}
        for i in items.values():self.catalogue[norm(i['title'])].append(i)
        self.conn=sqlite3.connect('file:'+str(Path(index).resolve())+'?mode=ro',uri=True,check_same_thread=False);self.conn.row_factory=sqlite3.Row
        tables={r[0] for r in self.conn.execute("select name from sqlite_master where type='table'")}
        # A complete index is looked up by name; an older titles-only index is read whole, as before.
        self.named='names' in tables;self.episodes=self.named and 'episodes' in tables
        if not self.named:
            for r in self.conn.execute("SELECT * FROM titles WHERE type IN ('movie','tvMovie','tvSeries','tvMiniSeries')"):
                r=dict(r);self.metadata[norm(r['title'])].append(r)
    def named_titles(self,key):
        if not self.named:return self.metadata.get(key,[])
        if key not in self.metadata:
            rows=[dict(r) for r in self.conn.execute("SELECT t.* FROM names n JOIN titles t ON t.id=n.id WHERE n.key=? AND t.type IN ('movie','tvMovie','tvSeries','tvMiniSeries')",(key,))]
            primary=[r for r in rows if norm(r['title'])==key]
            self.metadata[key]=primary or rows # an original-language title counts only when no primary title matches
        return self.metadata[key]
    def learn(self,titles):
        """Collect, across all profiles, which episode names were watched under each possible show name."""
        for title in titles:
            for base,episode,_,_,_ in splits(title):
                if episode:self.evidence[norm(base)].add(norm(episode))
    def episode_names(self,series_id):
        if series_id not in self.listed:
            self.listed[series_id]={r[0] for r in self.conn.execute('SELECT n.key FROM episodes e JOIN names n ON n.id=e.id WHERE e.parent=?',(series_id,))} if self.episodes else set()
        return self.listed[series_id]
    def supported(self,candidates,key,minimum):
        """The one candidate series whose episode list contains the watched episode names, else None."""
        watched=self.evidence.get(key,set())-{''}
        scores=sorted(((len(watched&self.episode_names(c['id'])),c['id'],c) for c in candidates if c['type'] in SERIES),key=lambda x:x[:2],reverse=True)
        # Enough of the watched names must be in the list: one coincidental match is not a fact.
        if not scores or scores[0][0]<minimum or scores[0][0]<.3*len(watched):return None
        if len(scores)>1 and scores[0][0]<3*scores[1][0]:return None
        return scores[0][2]
    def episode(self,title,at):
        """(season, episode) of a resolved episode row. The export's own numbers are used as given;
        the index only fills what the export leaves out (the season of a show listed without one)."""
        key=(title,at[:4]);item=self.cache.get(key);used=self.used.get(key)
        if not item or item['type']!='tv' or not used:return None
        _,name,_,season,number=used;series=self.imdb.get(item['id'])
        if season is not None and number is not None:return season,number
        if not series or not self.episodes:return None
        if number is not None:
            seasons={r[0] for r in self.conn.execute('SELECT DISTINCT season FROM episodes WHERE parent=? AND season>0',(series,))}
            if len(seasons)==1:return next(iter(seasons)),number # a show listed without a season has one season
        if not name:return None
        found={(r[0],r[1]) for r in self.conn.execute('SELECT e.season,e.episode FROM episodes e JOIN names n ON n.id=e.id WHERE e.parent=? AND n.key=?',(series,norm(name))) if r[0] is not None and r[1] is not None}
        if season is not None:found={f for f in found if f[0]==season} or found
        if number is not None:found={f for f in found if f[1]==number} or found
        return next(iter(found)) if len(found)==1 else None
    def total_episodes(self,item):
        series=self.imdb.get(item['id'])
        return self.conn.execute('SELECT COUNT(*) FROM episodes WHERE parent=? AND season IS NOT NULL AND season>0 AND episode IS NOT NULL',(series,)).fetchone()[0] if series and self.episodes else 0
    def resolve(self,title,at):
        key=(title,at[:4])
        if key in self.cache:return self.cache[key]
        latest=int(at[:4]);result=None;method=None
        for position,split in enumerate(splits(title)):
            base,episode,explicit,_,_=split
            year=re.search(r'\((19\d{2}|20\d{2})\)$',base)
            if year:base=base[:year.start()].strip()
            wanted=int(year[1]) if year else None;guess=episode is not None and not explicit # a colon-prefix read as "Show: Episode"
            typ='tv' if explicit or guess else None
            candidates=[m for m in self.named_titles(norm(base)) if (not typ or m['type'] in SERIES) and (not wanted or m['year']==wanted) and (not m['year'] or m['year']<=latest)]
            m=None
            if guess:
                # Only the export's own episode names can turn a prefix into a show.
                m=self.supported(candidates,norm(base),1 if len(candidates)==1 else 2);method='series before an episode name'
            elif len(candidates)==1:m=candidates[0];method='unique title'
            elif len(candidates)>1:
                films=[c for c in candidates if c['type'] not in SERIES]
                # A row with no season marker and no episode tag is not an episode, so one same-named film is the match.
                if not explicit and len(films)==1:m=films[0];method='unique movie title'
                # Otherwise remakes/type collisions stay unresolved unless the watched episodes settle it.
                else:m=self.supported(candidates,norm(base),2);method='episode names among same-named titles'
            if m:
                kind='tv' if m['type'] in SERIES else 'movie'
                canon=[i for i in self.catalogue.get(norm(m['title']),[]) if i['type']==kind and i['year']==str(m['year'])]
                result=dict(canon[0]) if len(canon)==1 else dict(id='history:imdb:'+m['id'],title=m['title'],year=str(m['year'] or ''),type=kind,genres=genre_tags(m['genres'].split(',')),metadata_id=m['id'])
                self.imdb[result['id']]=m['id']
            elif not candidates and not guess:
                canon=[i for i in self.catalogue.get(norm(base),[]) if (not typ or i['type']==typ) and (not wanted or i['year']==str(wanted)) and (not i['year'] or int(i['year'])<=latest)]
                if len(canon)==1:result=dict(canon[0]);method='catalogue title'
            if result:self.used[key]=split
            # Stop on a match, or when the whole title itself is ambiguous (a prefix must not override that).
            if result or (position==0 and not explicit and candidates):break
        if result:result['genres']=genre_tags(result['genres']);result['meta']=', '.join(result['genres']);self.methods[key]=method
        self.cache[key]=result;return result

def prepare(db,items,resolver,out,base_features=None):
    profiles=[];all_items=dict(items)
    resolver.learn([r[0] for r in db.execute("SELECT DISTINCT title FROM events WHERE kind='view' AND title IS NOT NULL")])
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
            if r['kind']=='view':counts['view_seconds']+=r['seconds']
            item=resolver.resolve(r['title'],r['at'])
            if not item:
                if r['kind']=='view':counts['unresolved_view_seconds']+=r['seconds']
                unresolved.append({'event':r['id'],'title':r['title'],'kind':r['kind'],'seconds':r['seconds'] or 0});continue
            counts['resolved by '+str(resolver.methods.get((r['title'],r['at'][:4])))]+=1
            counts['resolved_'+r['kind']+'_rows']+=1;all_items[item['id']]=item
            group=groups.setdefault(item['id'],{'item':item,'seconds':0,'position':0,'seen_at':None,'list_at':None,'preference':None,'preference_at':None,'episodes':{}})
            if r['kind']=='view':
                # Bookmark: how far into the title this play got. 0 is how the export writes "none".
                reached=seconds(r['bookmark']) or 0;counts['view_rows_with_position']+=bool(reached)
                group['seconds']+=r['seconds'];group['seen_at']=max(group['seen_at'] or '',r['at'])
                if item['type']=='movie':group['position']=max(group['position'],reached)
                elif ':' in r['title']:
                    # Keep which episode this was, not only which series.
                    counts['episode_rows']+=1;found=resolver.episode(r['title'],r['at'])
                    if found:
                        counts['episode_rows_numbered']+=1;episode=group['episodes'].setdefault(found,[0,0])
                        episode[0]+=r['seconds'];episode[1]=max(episode[1],reached)
            elif r['kind']=='list':group['list_at']=max(group['list_at'] or '',r['at'])
            elif group['preference_at'] is None or r['at']>=group['preference_at']:group['preference']=r['signal'];group['preference_at']=r['at']
        seeds=[];seen=[];feedback=[];negatives=[];viewing=[]
        for ident,g in groups.items():
            unseen=g['preference']=='unwatched' and (not g['seen_at'] or g['preference_at']>=g['seen_at'])
            if unseen:feedback.append(dict(FeedbackType='recommend_unwatched',UserId=p['id'],ItemId=ident,Value=1,Timestamp=g['preference_at'],Comment=OWNER))
            if g['seen_at'] and not unseen:
                seen.append(ident);feedback.append(dict(FeedbackType='watched',UserId=p['id'],ItemId=ident,Value=1,Timestamp=g['seen_at'],Comment=OWNER))
                # Viewing facts as the export states them. Whether they amount to "watched" is decided in watched.py only.
                viewing.append(dict(item=g['item'],metadata_id=resolver.imdb.get(ident),seconds=g['seconds'],position=g['position'] or None,at=g['seen_at'],
                    episodes=[[season,number,played,reached or None] for (season,number),(played,reached) in sorted(g['episodes'].items())],
                    total_episodes=resolver.total_episodes(g['item']) if g['episodes'] else 0))
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
        write(root/'matches.json',dict(profile=p['id'],profile_name=p['name'],scope='Netflix · '+p['name'],seeds=seeds,seen=sorted(set(seen)),review=[],negative_ids=negatives,viewing=viewing))
        write(root/'gorse-feedback.json',feedback);write(root/'unresolved.json',unresolved)
        features={i['id']:(base_features or {}).get(i['id'],dict(metadata_vector=vector(i),creators=[])) for i in list(items.values())+[s['item'] for s in seeds]};write(root/'recommendation-features.json',features)
        # Coverage by the weight that matters (watch time), not only by rows.
        counts['resolved_view_share']=round(1-counts['unresolved_view_seconds']/counts['view_seconds'],4) if counts['view_seconds'] else None
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
