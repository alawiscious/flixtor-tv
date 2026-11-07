#!/usr/bin/env python3
"""Map a local Amazon staging DB to verified FlixTor catalogue metadata.
Never reads raw export files. Unmatched/ambiguous source records stay untouched.
"""
import argparse, csv, json, re, sqlite3, unicodedata, urllib.request
from urllib.parse import quote
from pathlib import Path
from datetime import datetime, timezone

AMBIGUOUS = {'snatch','gladiator','thefather','theshining','pilot','episodeone','thebeginning','battlestargalactica','theoffice','life','thehunt','theprisoner','serenity','war of the worlds','thedeep','utopia','cinderella','thefix','12angrymen'}
AMBIGUOUS = {re.sub('[^a-z0-9]', '', s) for s in AMBIGUOUS}

def norm(s):
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', s).casefold())

def title_parts(title):
    year = re.search(r'\((19\d{2}|20\d{2})\)', title)
    series = bool(re.search(r'\bSeason\s+(?:\d+|One|Two)\b', title, re.I))
    base = re.split(r'[,\s–—-]*\(?Season\s+(?:\d+|One|Two)\b', title, flags=re.I)[0]
    # Only strip known provider presentation suffixes, never arbitrary title subtitles.
    base = re.sub(r'\s*[\[(](?:19\d{2}|20\d{2}|4K UHD|UHD|HD|OV|Theatrical/Rated Version|Director.s Cut)[\])]','', base, flags=re.I).strip()
    return norm(base), int(year[1]) if year else None, 'tv' if series else None

def catalogue(rows):
    out = {}
    for url, title, year, genres, image in rows:
        m = re.fullmatch(r'/watch/(movie|tv)/(\d+)/[^/]+', url)
        if not m or not genres: continue
        item_id = 'flixtor:' + m[1] + ':' + m[2]
        out[item_id] = dict(id=item_id, title=title, year=str(year), meta=genres,
            image=image if image.startswith('https://img.xcdn.to/') else 'https://img.xcdn.to/t/p/w342/' + image,
            url='https://flixtor.to'+url, type=m[1], genres=[g.strip() for g in genres.split(',') if g.strip()])
    return out

def resolve(title, items, force_type=None):
    key, year, typ = title_parts(title)
    if key in AMBIGUOUS and year is None: return None
    if not typ and not year and len(re.findall(r'\w+',title))<2:return None
    matches = [i for i in items.values() if norm(i['title'])==key and
               (not year or str(year)==i['year']) and (not (typ or force_type) or i['type']==(typ or force_type))]
    return matches[0] if len(matches)==1 else None

def match_history(db, items):
    conn=sqlite3.connect(db); seeds={}; seen={}; review=[]
    for source_id,title,added,deleted in conn.execute('select item_id,title,added_at,deleted from watchlist'):
        if deleted: continue
        # Historical additions are weak interest, not confirmed current list membership.
        item=resolve(title,items)
        if item:
            seeds[item['id']]={'item':item,'at':added,'source':'historical Amazon watchlist addition'}
            review.append({'source_id':source_id,'source_title':title,'canonical_id':item['id'],'signal':'watchlist interest'})
    # Episode names lack series IDs: use only movie matches for playback records.
    for source_id,title,seconds,last in conn.execute('select item_id,title,sum(seconds_viewed),max(started_at) from sessions group by item_id,title'):
        if len(re.findall(r'\w+',title))<2:continue
        item=resolve(title,items,'movie')
        if item and item['type']=='movie' and seconds>=120:
            seen[item['id']]={'item':item,'at':last}
            if seconds>=1200:
                seeds[item['id']]={'item':item,'at':last,'source':'at least 20 recorded minutes on Amazon'}
            review.append({'source_id':source_id,'source_title':title,'canonical_id':item['id'],'signal':'recorded viewing interest' if seconds>=1200 else 'seen'})
    conn.close()
    return seeds,seen,review

def call(path, payload=None, method=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request('http://127.0.0.1:8088'+path,data=data,headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)

def write_json(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--catalogue',required=True);p.add_argument('--out',required=True);p.add_argument('--apply',action='store_true');p.add_argument('--profile',default='ftv-amazon-import');a=p.parse_args()
    items=catalogue(json.loads(Path(a.catalogue).read_text())); seeds,seen,review=match_history(a.db,items)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    write_json(out/'catalogue.json',items)
    write_json(out/'matches.json',{'profile':a.profile,'seeds':list(seeds.values()),'seen':list(seen),'review':review})
    with (out/'canonical_mapping_review.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['source_id','source_title','canonical_id','signal']);w.writeheader();w.writerows(review)
    report={'catalogue_items':len(items),'interest_seeds':len(seeds),'seen_titles':len(seen),'matched_source_records':len(review),'applied':False}
    if a.apply:
        if not seeds:raise SystemExit('No reliable seeds: expand catalogue or review mappings first.')
        call('/api/items',[{'ItemId':i['id'],'IsHidden':False,'Categories':['playable',i['type']],'Labels':{'genres':i['genres'],'title':i['title'],'year':i['year'],'provider':'flixtor'},'Comment':i['title']} for i in items.values()],'POST')
        feedback=[]
        for kind,records in [('import_interest',seeds),('watched',seen)]:
            for item_id,record in records.items():
                feedback.append({'FeedbackType':kind,'UserId':a.profile,'ItemId':item_id,'Value':1,'Timestamp':record['at'],'Comment':record.get('source','Canonical match of recorded Amazon viewing')})
        expected={(f['FeedbackType'],f['ItemId']) for f in feedback}
        previous=call('/api/user/'+quote(a.profile,safe='')+'/feedback')
        owned_comments={'historical Amazon watchlist addition','at least 20 recorded minutes on Amazon','Canonical match of recorded Amazon viewing'}
        removed=[]
        for old in previous:
            key=(old['FeedbackType'],old['ItemId'])
            if key not in expected and key[0] in {'import_interest','watched'} and key[1].startswith('flixtor:') and old.get('Comment') in owned_comments:
                removed.append(old)
        if removed:
            write_json(out/'superseded_feedback.json',removed)
            for old in removed:call('/api/feedback/'+quote(old['FeedbackType'],safe='')+'/'+quote(a.profile,safe='')+'/'+quote(old['ItemId'],safe=''),method='DELETE')
        call('/api/feedback',feedback,'PUT')
        user=call('/api/user/'+quote(a.profile,safe=''))
        user['Labels'].update({'catalogue_mapping':'partial','matched_seeds':len(seeds)})
        call('/api/users',[user],'POST')
        conf=call('/api/dashboard/config'); before=conf['recommend']
        backup=out/'gorse_recommend_config_before.json'
        if not backup.exists():backup.write_text(json.dumps(before,indent=2))
        positives=before['data_source']['positive_feedback_types']
        if 'import_interest' not in positives:positives.append('import_interest')
        call('/api/dashboard/config',{'recommend':before},'POST') # schedules immediate index refresh
        actual=call('/api/user/'+a.profile+'/feedback')
        keys={(f['FeedbackType'],f['ItemId']) for f in actual}
        assert all((f['FeedbackType'],f['ItemId']) in keys for f in feedback)
        report['applied']=True;report['feedback_verified']=len(feedback)
    (out/'recommendation_import_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
