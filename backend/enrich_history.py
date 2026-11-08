#!/usr/bin/env python3
"""Resolve Amazon observations locally with bulk metadata; never search the web for history.
Uncertain title collisions stay unresolved. Episode matches need independently supported
series identity. Bulk IMDb data remains outside the public repository.
"""
import collections,json,re,sqlite3
from pathlib import Path
from history_index import parts,norm

MOVIES={'movie','tvMovie'}
SERIES={'tvSeries','tvMiniSeries'}
PROMO=re.compile(r'\b(?:teaser|trailer|sneak peek|preview)\b',re.I)


def genre_tags(genres):
    out=[]
    mapping={'Sci-Fi':['Science-Fiction'],'Sci-Fi-Fantasy':['Science-Fiction','Fantasy'],
             'Action-Adventure':['Action','Adventure'],'Kids':['Family'],'War-Politics':['War','Politics'],'TV-Movie':[]}
    for value in genres:
        for tag in mapping.get(value,[value]):
            if tag and tag!='\\N' and tag not in out:out.append(tag)
    return out


def observations(db,feedback):
    conn=sqlite3.connect(db);out=[]
    for ident,title,seconds,last,end in conn.execute('select item_id,title,sum(seconds_viewed),max(started_at),max(end_seconds) from sessions group by item_id,title'):
        if seconds>=120 and not PROMO.search(title):out.append(dict(source_id=ident,title=title,seconds=seconds,at=last,kind='playback',end=end))
    for ident,title,seconds,last,deleted in conn.execute('select item_id,title,seconds_watched,last_watched_at,deleted from watch_summaries'):
        if not deleted and seconds and seconds>=120 and last and not PROMO.search(title):out.append(dict(source_id=ident,title=title,seconds=seconds,at=last,kind='summary',end=None))
    for ident,title,at,deleted in conn.execute('select item_id,title,added_at,deleted from watchlist'):
        if not deleted and at:out.append(dict(source_id=ident,title=title,seconds=0,at=at,kind='watchlist',end=None))
    for n,row in enumerate(feedback):
        typ=row.get('Entity Type','');kind=row.get('Feedback Type','').casefold()
        if kind not in {'like','dislike'}:continue
        out.append(dict(source_id='amazon:explicit:'+str(n),title=row['Title Name'],seconds=0,at=row['Feedback Date'],kind=kind,end=None,force='tv' if typ=='TV Series' else 'movie' if typ=='Movie' else None))
    conn.close();return out


class Resolver:
    def __init__(self,index):
        self.conn=sqlite3.connect(index);self.conn.row_factory=sqlite3.Row;self.cache={};self.title_cache={};self.series_names=None
    def title(self,ident):
        if ident not in self.title_cache:
            row=self.conn.execute('select * from titles where id=?',(ident,)).fetchone();self.title_cache[ident]=dict(row) if row else None
        return self.title_cache[ident]
    def explicit_series(self,record):
        season=re.search(r'\bSeason\s+(?:\d+|One|Two|Three|Four|Five)\b',record['title'],re.I)
        if not season:return [],None
        if self.series_names is None:
            self.series_names=collections.defaultdict(list)
            for row in self.conn.execute("select * from titles where type in ('tvSeries','tvMiniSeries')"):
                self.series_names[norm(row['title'])].append(dict(row))
        stem=record['title'][:season.start()].strip(' ,–—-')
        chunks=[(stem,None)]
        for match in re.finditer(r'[-–—]',stem):chunks.append((stem[match.end():].strip(),stem[:match.start()].strip(' \"“”')))
        _,year,_=parts(record['title']);latest=int(record['at'][:4]);found=[]
        for name,ep in chunks:
            key,_,_=parts(name)
            candidates=[m for m in self.series_names.get(key,[]) if (not year or m['year']==year) and (not m['year'] or m['year']<=latest)]
            if candidates:found.extend((m,ep) for m in candidates)
        ids={m['id'] for m,ep in found}
        return [m for m,ep in found],next((ep for m,ep in found if ep),None)
    def candidates(self,record):
        key,year,typ=parts(record['title']);typ=typ or record.get('force')
        if key not in self.cache:
            self.cache[key]=[dict(r) for r in self.conn.execute('select t.*,e.parent,e.season,e.episode,coalesce(v.votes,0) as votes from names n join titles t on n.id=t.id left join episodes e on e.id=t.id left join votes v on v.id=t.id where n.key=?',(key,))]
        matches=[]
        latest=int(record['at'][:4]) if record.get('at') else 2100
        for item in self.cache[key]:
            if year and item['year']!=year:continue
            if item['year'] and item['year']>latest:continue
            if typ and item['type'] not in (SERIES if typ=='tv' else MOVIES):continue
            if record.get('end') and item['runtime'] and item['type'] in MOVIES|{'tvEpisode'} and record['end']>item['runtime']*60+180:continue
            matches.append(item)
        return matches
    def direct(self,candidates):
        # Multiple seasons/episodes can share a title; only their common parent is relevant.
        ids={c.get('parent') if c['type']=='tvEpisode' else c['id'] for c in candidates}
        ids.discard(None)
        if len(ids)!=1 or not candidates:return None
        ident=next(iter(ids));item=self.title(ident)
        return item if item and item['type'] in MOVIES|SERIES else None


def enrich(db,index,items,feedback=()):
    rows=observations(db,feedback);resolver=Resolver(index);candidates=[resolver.candidates(r) for r in rows]
    anchors=collections.defaultdict(set)
    explicit=[]
    for record in rows:
        choices,ep=resolver.explicit_series(record);explicit.append((choices,ep))
        if len({m['id'] for m in choices})==1:anchors[choices[0]['id']].add('explicit-series')
    for record,choices in zip(rows,candidates):
        item=resolver.direct(choices)
        if not item or item['type'] not in SERIES:continue
        if any(c['type']=='tvEpisode' for c in choices):anchors[item['id']].add(parts(record['title'])[0])
        elif record['kind'] in {'watchlist','like'} or parts(record['title'])[2]=='tv':anchors[item['id']].add('explicit-series')
    supported={ident for ident,names in anchors.items() if len(names)>=2 or 'explicit-series' in names}
    resolved=[];unresolved=[]
    for record,choices,(declared,episode_key) in zip(rows,candidates,explicit):
        item=resolver.direct(choices);method='unique title and type/year constraints'
        episode=any(c['type']=='tvEpisode' for c in choices)
        if episode:
            parents={c.get('parent') for c in choices if c['type']=='tvEpisode'} & supported
            direct_non_episode={c['id'] for c in choices if c['type']!='tvEpisode'}
            if len(parents)==1 and (not direct_non_episode or item and item['id'] in parents):
                item=resolver.title(next(iter(parents)));method='episode title within independently supported series'
            else:
                # A movie can share its name with many review/podcast episodes.
                # Ignore those unsupported episode parents only when exactly one
                # full movie remains and it has substantial independent metadata.
                movies=[c for c in choices if c['type'] in MOVIES]
                if not parents and len(movies)==1 and movies[0].get('votes',0)>=1000:
                    item=movies[0];method='unique full-length movie; review episode collisions excluded'
                else:item=None
        if declared:
            declared_ids={m['id'] for m in declared}
            eligible=declared if len(declared_ids)==1 else [m for m in declared if m['id'] in supported]
            if len({m['id'] for m in eligible})==1:
                item=eligible[0];method='episode with explicit series/season in source' if episode_key else 'explicit series/season title in source'
                record=dict(record,episode_key=norm(episode_key) if episode_key else None)
        if not item:
            reason='no metadata candidate' if not choices else 'ambiguous title or unsupported episode parent'
            unresolved.append(dict(source_id=record['source_id'],title=record['title'],kind=record['kind'],reason=reason,candidates=len(choices)))
        else:resolved.append(dict(record,item=item,method=method))
    # Deduplicate playback and watch-summary observations by normalized source title.
    # Duration uses max across these two sources, never their sum.
    groups={}
    for row in resolved:
        item=row['item'];ident=item['id'];g=groups.setdefault(ident,dict(metadata=item,events=[],observations={}))
        g['events'].append(row)
        if row['kind'] in {'playback','summary'}:
            key=row.get('episode_key') or parts(row['title'])[0];g['observations'][key]=max(g['observations'].get(key,0),row['seconds'])
    seeds={};seen=set();seen_at={};excluded=set();crosswalk={};review=[]
    for ident,g in groups.items():
        m=g['metadata'];typ='tv' if m['type'] in SERIES else 'movie';genres=genre_tags(m['genres'].split(','))
        canonical=[i for i in items.values() if norm(i['title'])==norm(m['title']) and i['type']==typ and i['year']==str(m['year'])]
        item=dict(canonical[0]) if len(canonical)==1 else dict(id='history:imdb:'+ident,title=m['title'],year=str(m['year'] or ''),type=typ,genres=genres,meta=', '.join(genres),metadata_id=ident)
        item['genres']=genre_tags(item['genres']);crosswalk[ident]=item['id']
        kinds={r['kind'] for r in g['events']};seconds=sum(g['observations'].values());at=max(r['at'] for r in g['events'])
        if g['observations'] and len(canonical)==1:
            seen.add(item['id']);seen_at[item['id']]=max(r['at'] for r in g['events'] if r['kind'] in {'playback','summary'})
        explicit=sorted((r for r in g['events'] if r['kind'] in {'like','dislike'}),key=lambda r:r['at'])
        kinds-= {'like','dislike'}
        if explicit:kinds.add(explicit[-1]['kind'])
        if 'dislike' in kinds:
            excluded.add(item['id']);continue
        if not genres:continue
        if 'like' in kinds or 'watchlist' in kinds or seconds>=1200:
            signal='explicit Amazon like' if 'like' in kinds else 'historical Amazon watchlist addition' if 'watchlist' in kinds else 'recorded Amazon viewing resolved with IMDb metadata'
            seeds[item['id']]=dict(item=item,at=at,source=signal,feedback_type='like' if 'like' in kinds else 'import_interest',recorded_seconds=seconds,episode_title_count=len(g['observations']) if typ=='tv' else 0)
        for row in g['events']:review.append(dict(source_id=row['source_id'],source_title=row['title'],canonical_id=item['id'],signal=row['kind'],method=row['method'],metadata_id=ident))
    report=dict(source_observations=len(rows),resolved_observations=len(resolved),resolved_titles=len(groups),
                resolved_episode_observations=sum(r['method'].startswith('episode') for r in resolved),
                supported_series=len(supported),metadata_interest_titles=len(seeds),explicit_likes_resolved=sum(s.get('feedback_type')=='like' for s in seeds.values()),
                unresolved_observations=len(unresolved),unresolved_reasons=dict(collections.Counter(r['reason'] for r in unresolved)),
                matched_playback_source_ids=sorted({r['source_id'] for r in resolved if r['kind']=='playback'}))
    resolver.conn.close()
    return dict(seeds=seeds,seen=seen,seen_at=seen_at,excluded=excluded,review=review,unresolved=unresolved,report=report)
