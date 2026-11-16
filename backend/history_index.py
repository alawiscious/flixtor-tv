#!/usr/bin/env python3
"""Local, targeted index of official IMDb bulk data. No viewing-title network requests.
Information courtesy of IMDb (https://www.imdb.com). Used with permission.
Datasets are retained privately for individual personal, non-commercial use.
"""
import argparse,gzip,json,os,re,sqlite3,unicodedata
from datetime import datetime,timezone
from pathlib import Path


def norm(text):
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',text).casefold())


def parts(text):
    year=re.search(r'\((19\d{2}|20\d{2})\)',text)
    season=re.search(r'\bSeason\s+(?:\d+|One|Two|Three|Four|Five)\b',text,re.I)
    base=text[:season.start()] if season else text
    base=re.sub(r'\s*[\[(](?:19\d{2}|20\d{2}|4K UHD|UHD|HD|OV|Theatrical/Rated Version|Director.s Cut)[\])]','',base,flags=re.I)
    return norm(base),int(year[1]) if year else None,'tv' if season else None


FULL_TYPES={'movie','tvMovie','tvSeries','tvMiniSeries'}
SERIES_TYPES={'tvSeries','tvMiniSeries'}
COVERAGE=('names: every non-adult movie, tvMovie, tvSeries and tvMiniSeries, by primary and original title. '
          'Shorts, videos and episodes are indexed only when their name matches a history key. '
          'episodes: the full episode list of every series whose name matches a history key, plus any episode whose own name matches one.')


def title_keys(title):
    """Every key a recorded title can be looked up by: the title itself (via parts), each
    colon-prefix ("Show" of "Show: Season 1: Episode") and the last colon segment (an episode name)."""
    segments=[x.strip() for x in title.split(':') if x.strip()]
    found={parts(title)[0]}
    for n in range(1,len(segments)+1):found.add(parts(': '.join(segments[:n]))[0])
    if segments:found.add(norm(segments[-1]))
    found.discard('');return found


def build_index(basics,episodes,destination,keys,ratings=None,sources=None):
    """keys: normalized names seen in any history source. sources: what those keys came from,
    recorded in the index so a later reader can tell what it covers (see COVERAGE)."""
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=destination.with_name(destination.name+'.building-'+str(os.getpid()))
    conn=sqlite3.connect(temporary)
    conn.executescript('DROP TABLE IF EXISTS titles; DROP TABLE IF EXISTS names; DROP TABLE IF EXISTS episodes; DROP TABLE IF EXISTS votes; DROP TABLE IF EXISTS meta; CREATE TABLE titles(id TEXT PRIMARY KEY,type TEXT,title TEXT,year INTEGER,runtime INTEGER,genres TEXT); CREATE TABLE names(key TEXT,id TEXT,PRIMARY KEY(key,id)); CREATE TABLE episodes(id TEXT PRIMARY KEY,parent TEXT,season INTEGER,episode INTEGER); CREATE TABLE votes(id TEXT PRIMARY KEY,votes INTEGER); CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);')
    def number(x):return int(x) if x.isdigit() else None
    def rows(path,width):
        with gzip.open(path,'rt',encoding='utf-8') as f:
            next(f)
            for line in f:
                row=line.rstrip('\n').split('\t')
                if len(row)==width:yield row
    def flush(batch,names):
        conn.executemany('INSERT OR IGNORE INTO titles VALUES (?,?,?,?,?,?)',batch);conn.executemany('INSERT OR IGNORE INTO names VALUES (?,?)',names)
    wanted_episodes=set();history_series=set();batch=[];names=[]
    for ident,kind,title,original,adult,year,_,runtime,genres in rows(basics,9):
        if adult!='0' or kind not in FULL_TYPES|{'video','short','tvEpisode'}:continue
        own={norm(title),norm(original)}-{''};matched=own&keys
        if not matched and kind not in FULL_TYPES:continue
        batch.append((ident,kind,title,number(year),number(runtime),genres))
        names.extend((k,ident) for k in (own if kind in FULL_TYPES else matched))
        if matched and kind=='tvEpisode':wanted_episodes.add(ident)
        if matched and kind in SERIES_TYPES:history_series.add(ident)
        if len(batch)>=5000:flush(batch,names);batch=[];names=[]
    flush(batch,names)
    links=[(row[0],row[1],number(row[2]),number(row[3])) for row in rows(episodes,4) if row[0] in wanted_episodes or row[1] in history_series]
    conn.executemany('INSERT OR IGNORE INTO episodes VALUES (?,?,?,?)',links)
    # Episodes of history series were skipped above unless their own name matched; add them by name now.
    listed={link[0] for link in links}-wanted_episodes;batch=[];names=[]
    if listed:
        for ident,kind,title,original,adult,year,_,runtime,genres in rows(basics,9):
            if ident not in listed or adult!='0':continue
            batch.append((ident,kind,title,number(year),number(runtime),genres));names.extend((k,ident) for k in {norm(title),norm(original)}-{''})
            if len(batch)>=5000:flush(batch,names);batch=[];names=[]
        flush(batch,names)
    # Readers go from a series to its episodes and from an episode to its names; both need an index.
    conn.execute('CREATE INDEX episodes_parent ON episodes(parent)');conn.execute('CREATE INDEX names_id ON names(id)')
    if ratings:
        candidate_ids={r[0] for r in conn.execute('select id from names')}
        conn.executemany('INSERT OR REPLACE INTO votes VALUES (?,?)',[(row[0],int(row[2])) for row in rows(ratings,3) if row[0] in candidate_ids])
    report={'indexed_titles':conn.execute('select count(*) from titles').fetchone()[0],'candidate_names':conn.execute('select count(*) from names').fetchone()[0],'episode_links':len(links),'history_series':len(history_series)}
    conn.executemany('INSERT INTO meta VALUES (?,?)',[('built_at',datetime.now(timezone.utc).isoformat()),('coverage',COVERAGE),('history_keys',str(len(keys))),('sources',json.dumps(sources or [])),('report',json.dumps(report))])
    conn.commit();print(json.dumps(report),flush=True);conn.close();temporary.replace(destination)

def main():
    p=argparse.ArgumentParser();p.add_argument('--basics',required=True);p.add_argument('--episodes',required=True);p.add_argument('--db',required=True);p.add_argument('--out',required=True);p.add_argument('--catalogue');p.add_argument('--ratings');p.add_argument('--feedback')
    p.add_argument('--netflix-db',help='Staged Netflix events; without it the index cannot resolve Netflix episode names');a=p.parse_args()
    # Every history source contributes keys. A source added later means this index must be rebuilt.
    sources=[];keys=set()
    def add(label,titles):
        before=len(keys)
        for title in titles:keys.update(title_keys(title))
        sources.append({'source':label,'titles':len(titles),'new_keys':len(keys)-before})
    source=sqlite3.connect(a.db);add('amazon',[t for t, in source.execute('select title from items')]);source.close()
    if a.netflix_db:
        source=sqlite3.connect('file:'+str(Path(a.netflix_db).resolve())+'?mode=ro',uri=True);add('netflix',[t for t, in source.execute('select distinct title from events where title is not null')]);source.close()
    if a.feedback:add('amazon feedback',[r['Title Name'] for r in json.loads(Path(a.feedback).read_text())])
    if a.catalogue:
        before=len(keys);keys.update(norm(i['title']) for i in json.loads(Path(a.catalogue).read_text()).values());sources.append({'source':'catalogue','new_keys':len(keys)-before})
    build_index(a.basics,a.episodes,a.out,keys,a.ratings,sources)
if __name__=='__main__':main()
