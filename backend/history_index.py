#!/usr/bin/env python3
"""Local, targeted index of official IMDb bulk data. No viewing-title network requests.
Information courtesy of IMDb (https://www.imdb.com). Used with permission.
Datasets are retained privately for individual personal, non-commercial use.
"""
import argparse,gzip,json,os,re,sqlite3,unicodedata
from pathlib import Path


def norm(text):
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',text).casefold())


def parts(text):
    year=re.search(r'\((19\d{2}|20\d{2})\)',text)
    season=re.search(r'\bSeason\s+(?:\d+|One|Two|Three|Four|Five)\b',text,re.I)
    base=text[:season.start()] if season else text
    base=re.sub(r'\s*[\[(](?:19\d{2}|20\d{2}|4K UHD|UHD|HD|OV|Theatrical/Rated Version|Director.s Cut)[\])]','',base,flags=re.I)
    return norm(base),int(year[1]) if year else None,'tv' if season else None


def build_index(basics,episodes,destination,keys,ratings=None):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=destination.with_name(destination.name+'.building-'+str(os.getpid()))
    conn=sqlite3.connect(temporary)
    conn.executescript('DROP TABLE IF EXISTS titles; DROP TABLE IF EXISTS names; DROP TABLE IF EXISTS episodes; DROP TABLE IF EXISTS votes; CREATE TABLE titles(id TEXT PRIMARY KEY,type TEXT,title TEXT,year INTEGER,runtime INTEGER,genres TEXT); CREATE TABLE names(key TEXT,id TEXT,PRIMARY KEY(key,id)); CREATE TABLE episodes(id TEXT PRIMARY KEY,parent TEXT,season INTEGER,episode INTEGER); CREATE TABLE votes(id TEXT PRIMARY KEY,votes INTEGER);')
    def number(x):return int(x) if x.isdigit() else None
    wanted_episodes=set();batch=[];names=[];count=0
    with gzip.open(basics,'rt',encoding='utf-8') as f:
        next(f)
        for line in f:
            row=line.rstrip('\n').split('\t')
            if len(row)!=9:continue
            ident,kind,title,original,adult,year,_,runtime,genres=row
            if adult!='0' or kind not in {'movie','tvMovie','video','short','tvSeries','tvMiniSeries','tvEpisode'}:continue
            title_keys={norm(title),norm(original)} & keys
            if not title_keys and kind not in {'tvSeries','tvMiniSeries'}:continue
            batch.append((ident,kind,title,number(year),number(runtime),genres))
            names.extend((k,ident) for k in title_keys)
            if title_keys and kind=='tvEpisode':wanted_episodes.add(ident)
            if len(batch)>=5000:
                conn.executemany('INSERT OR IGNORE INTO titles VALUES (?,?,?,?,?,?)',batch);conn.executemany('INSERT OR IGNORE INTO names VALUES (?,?)',names);count+=len(batch);batch=[];names=[]
        conn.executemany('INSERT OR IGNORE INTO titles VALUES (?,?,?,?,?,?)',batch);conn.executemany('INSERT OR IGNORE INTO names VALUES (?,?)',names)
    batch=[]
    with gzip.open(episodes,'rt',encoding='utf-8') as f:
        next(f)
        for line in f:
            row=line.rstrip('\n').split('\t')
            if len(row)==4 and row[0] in wanted_episodes:batch.append((row[0],row[1],number(row[2]),number(row[3])))
    conn.executemany('INSERT OR IGNORE INTO episodes VALUES (?,?,?,?)',batch)
    if ratings:
        candidate_ids={r[0] for r in conn.execute('select id from names')};votes=[]
        with gzip.open(ratings,'rt',encoding='utf-8') as f:
            next(f)
            for line in f:
                row=line.rstrip('\n').split('\t')
                if len(row)==3 and row[0] in candidate_ids:votes.append((row[0],int(row[2])))
        conn.executemany('INSERT OR REPLACE INTO votes VALUES (?,?)',votes)
    conn.commit();print(json.dumps({'indexed_titles':conn.execute('select count(*) from titles').fetchone()[0],'candidate_names':conn.execute('select count(*) from names').fetchone()[0],'episode_links':len(batch)}),flush=True);conn.close();temporary.replace(destination)


def main():
    p=argparse.ArgumentParser();p.add_argument('--basics',required=True);p.add_argument('--episodes',required=True);p.add_argument('--db',required=True);p.add_argument('--out',required=True);p.add_argument('--catalogue');p.add_argument('--ratings');p.add_argument('--feedback');a=p.parse_args()
    source=sqlite3.connect(a.db);keys={parts(t)[0] for t, in source.execute('select title from items')};source.close()
    if a.feedback:keys.update(parts(r['Title Name'])[0] for r in json.loads(Path(a.feedback).read_text()))
    if a.catalogue:keys.update(norm(i['title']) for i in json.loads(Path(a.catalogue).read_text()).values())
    build_index(a.basics,a.episodes,a.out,keys,a.ratings)
if __name__=='__main__':main()
