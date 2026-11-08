#!/usr/bin/env python3
"""Map a local Amazon staging DB to verified FlixTor catalogue metadata.
Never reads raw export files. Unmatched/ambiguous source records stay untouched.
"""
import argparse, csv, json, re, sqlite3, unicodedata, urllib.request
from urllib.parse import quote
from pathlib import Path
from datetime import datetime, timezone
from enrich_history import enrich,genre_tags

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
    # Watch Events summaries are a second observation of viewing, not extra
    # sessions to add to playback duration. They can recover titles missing from
    # playback rows. Series require an explicit season-qualified title.
    if conn.execute("select 1 from sqlite_master where type='table' and name='watch_summaries'").fetchone():
        for source_id,title,seconds,last,deleted in conn.execute('select item_id,title,seconds_watched,last_watched_at,deleted from watch_summaries'):
            if deleted or not seconds or seconds<120 or not last:continue
            _,_,typ=title_parts(title)
            item=resolve(title,items,typ or 'movie')
            if not item:continue
            if item['id'] not in seen:seen[item['id']]={'item':item,'at':last}
            if seconds>=1200 and item['id'] not in seeds:
                seeds[item['id']]={'item':item,'at':last,'source':'at least 20 recorded minutes in Amazon watch summary'}
            review.append({'source_id':source_id,'source_title':title,'canonical_id':item['id'],'signal':'watch summary interest' if seconds>=1200 else 'watch summary seen'})
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
    index=out.parent/'metadata/title-index.sqlite'
    metadata_report=None;excluded=set()
    if index.exists():
        feedback_path=out.parent/'metadata/explicit-feedback.json'
        enriched=enrich(a.db,index,items,json.loads(feedback_path.read_text()) if feedback_path.exists() else [])
        seeds.update(enriched['seeds']);excluded=enriched['excluded']
        for item_id in excluded:seeds.pop(item_id,None)
        for item_id in enriched['seen']:
            if item_id not in seen:seen[item_id]={'item':items[item_id],'at':enriched['seen_at'][item_id]}
        review.extend({k:r[k] for k in ['source_id','source_title','canonical_id','signal']} for r in enriched['review'])
        write_json(out/'metadata_mapping_review.json',enriched['review'])
        write_json(out/'unresolved_mapping_review.json',enriched['unresolved'])
        metadata_report=enriched['report']
    for item in items.values():item['genres']=genre_tags(item['genres'])
    write_json(out/'catalogue.json',items)
    write_json(out/'matches.json',{'profile':a.profile,'seeds':sorted(seeds.values(),key=lambda r:(r.get('feedback_type')=='like',r['at']),reverse=True),'seen':list(set(seen)|excluded),'review':review,'metadata_coverage':metadata_report})
    with (out/'canonical_mapping_review.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['source_id','source_title','canonical_id','signal']);w.writeheader();w.writerows(review)
    conn=sqlite3.connect(a.db)
    source_count=conn.execute('select count(*) from items').fetchone()[0]
    session_count=conn.execute('select count(*) from sessions').fetchone()[0]
    source_ids={r[0] for r in conn.execute('select item_id from items')}
    matched_ids={r['source_id'] for r in review}&source_ids
    coverage={'source_items':source_count,'retained_viewing_sessions':session_count,
              'matched_source_items':len(matched_ids),
              'unmatched_source_items':source_count-len(matched_ids),
              'limitation':'Uncertain identities remain unresolved; playback and summary durations are not added together. History-only metadata can teach taste but is never a playable result.'}
    if metadata_report:
        matched_playback=set(metadata_report['matched_playback_source_ids'])
        coverage['matched_viewing_sessions']=sum(1 for ident, in conn.execute('select item_id from sessions') if ident in matched_playback)
        coverage['resolved_films_and_series']=metadata_report['resolved_titles']
        coverage['resolved_episode_observations']=metadata_report['resolved_episode_observations']
        coverage['explicit_likes_resolved']=metadata_report['explicit_likes_resolved']
    conn.close()
    write_json(out/'coverage_report.json',coverage)
    report={'coverage':coverage,'catalogue_items':len(items),'interest_seeds':len(seeds),'seen_titles':len(seen),'matched_source_records':len(review),'applied':False}
    if a.apply:
        if not seeds:raise SystemExit('No reliable seeds: expand catalogue or review mappings first.')
        call('/api/items',[{'ItemId':i['id'],'IsHidden':False,'Categories':['playable',i['type']],'Labels':{'genres':i['genres'],'title':i['title'],'year':i['year'],'provider':'flixtor'},'Comment':i['title']} for i in items.values()],'POST')
        history_items=[s['item'] for s in seeds.values() if s['item']['id'] not in items]
        if history_items:call('/api/items',[{'ItemId':i['id'],'IsHidden':True,'Categories':['history-only',i['type']],'Labels':{'genres':i['genres'],'title':i['title'],'year':i['year'],'provider':'imdb'},'Comment':i['title']} for i in history_items],'POST')
        feedback=[]
        for kind,records in [('import_interest',seeds),('watched',seen)]:
            for item_id,record in records.items():
                feedback.append({'FeedbackType':record.get('feedback_type',kind) if kind=='import_interest' else kind,'UserId':a.profile,'ItemId':item_id,'Value':1,'Timestamp':record['at'],'Comment':record.get('source','Canonical match of recorded Amazon viewing')})
        expected={(f['FeedbackType'],f['ItemId']) for f in feedback}
        previous=call('/api/user/'+quote(a.profile,safe='')+'/feedback')
        owned_comments={'historical Amazon watchlist addition','at least 20 recorded minutes on Amazon','Canonical match of recorded Amazon viewing','at least 20 recorded minutes in Amazon watch summary','recorded Amazon viewing resolved with IMDb metadata','explicit Amazon like'}
        removed=[]
        for old in previous:
            key=(old['FeedbackType'],old['ItemId'])
            if key not in expected and key[0] in {'import_interest','watched','like'} and key[1].startswith(('flixtor:','history:imdb:')) and old.get('Comment') in owned_comments:
                removed.append(old)
        if removed:
            write_json(out/'superseded_feedback.json',removed)
            for old in removed:call('/api/feedback/'+quote(old['FeedbackType'],safe='')+'/'+quote(a.profile,safe='')+'/'+quote(old['ItemId'],safe=''),method='DELETE')
        call('/api/feedback',feedback,'PUT')
        user=call('/api/user/'+quote(a.profile,safe=''))
        user['Labels'].update({'catalogue_mapping':'partial','matched_seeds':len(seeds),'history_metadata':'local IMDb bulk index' if metadata_report else 'catalogue only'})
        call('/api/users',[user],'POST')
        conf=call('/api/dashboard/config'); before=conf['recommend']
        backup=out/'gorse_recommend_config_before.json'
        if not backup.exists():backup.write_text(json.dumps(before,indent=2))
        positives=before['data_source']['positive_feedback_types']
        for feedback_type in ['import_interest','like']:
            if feedback_type not in positives:positives.append(feedback_type)
        # Online recommendation defaults considered only the latest 100 seeds.
        before['context_size']=max(512,before.get('context_size',100),len(seeds)+20)
        call('/api/dashboard/config',{'recommend':before},'POST') # schedules immediate index refresh
        actual=call('/api/user/'+a.profile+'/feedback')
        keys={(f['FeedbackType'],f['ItemId']) for f in actual}
        assert all((f['FeedbackType'],f['ItemId']) in keys for f in feedback)
        if (out/'feature-inputs.json').exists():
            from recommendation_features import enrich_features
            enrich_features(out)
        report['applied']=True;report['feedback_verified']=len(feedback)
    (out/'recommendation_import_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
