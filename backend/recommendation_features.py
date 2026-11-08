"""Local content features for Gorse: genres, era, media type, directors and writers."""
import argparse,gzip,json,math,sqlite3
from pathlib import Path
from enrich_history import genre_tags
from history_index import norm
from personalize import call

GENRES=['Action','Adventure','Animation','Biography','Comedy','Crime','Documentary','Drama','Family','Fantasy','Film-Noir','History','Horror','Music','Musical','Mystery','News','Reality-TV','Romance','Science-Fiction','Sport','Talk-Show','Thriller','War','Western']

def vector(item):
    genres=set(genre_tags(item.get('genres',[])));year=int(item.get('year') or 2000)
    values=[float(g in genres) for g in GENRES]
    values += [.3*math.exp(-((year-center)/15)**2/2) for center in [1940,1960,1980,1990,2000,2010,2020,2030]]
    values += [.35*float(item.get('type')==kind) for kind in ['movie','tv']]
    length=math.sqrt(sum(v*v for v in values)) or 1
    return [round(v/length,6) for v in values]

def enrich_features(root,crew=None):
    root=Path(root)
    inputs_path=root/'feature-inputs.json'
    saved=json.loads(inputs_path.read_text()) if inputs_path.exists() else {}
    crew=crew or saved.get('crew')
    if crew:inputs_path.write_text(json.dumps({'crew':str(crew)}))
    items=json.loads((root/'catalogue.json').read_text());matched=json.loads((root/'matches.json').read_text())
    all_items={**items,**{s['item']['id']:s['item'] for s in matched['seeds']}}
    db=sqlite3.connect(root.parent/'metadata/title-index.sqlite');db.row_factory=sqlite3.Row
    names={}
    for row in db.execute('select t.* from titles t join names n on t.id=n.id'):
        names.setdefault(norm(row['title']),{})[row['id']]=dict(row)
    db.close()
    metadata={}
    for ident,item in all_items.items():
        source_id=item.get('metadata_id')
        if not source_id:
            candidates=[r for r in names.get(norm(item['title']),{}).values() if str(r['year'])==item['year'] and (r['type'] in {'tvSeries','tvMiniSeries'})==(item['type']=='tv') and r['type'] in {'movie','tvMovie','tvSeries','tvMiniSeries'}]
            if len(candidates)==1:source_id=candidates[0]['id']
        metadata[ident]=dict(source_id=source_id,metadata_vector=vector(item),creators=[])
    lookup={entry['source_id']:[] for entry in metadata.values() if entry['source_id']}
    if crew and Path(crew).exists():
        with gzip.open(crew,'rt') as f:
            next(f)
            for line in f:
                fields=line.rstrip('\n').split('\t')
                if len(fields)==3 and fields[0] in lookup:
                    lookup[fields[0]]=['director:'+n for n in fields[1].split(',') if n!='\\N']+['writer:'+n for n in fields[2].split(',') if n!='\\N']
    for entry in metadata.values():entry['creators']=lookup.get(entry['source_id'],[])
    (root/'recommendation-features.json').write_text(json.dumps(metadata))
    payload=[]
    for ident,item in all_items.items():
        entry=metadata[ident]
        payload.append({'ItemId':ident,'IsHidden':ident not in items,'Categories':['playable' if ident in items else 'history-only',item['type']],'Labels':{'genres':genre_tags(item['genres']),'title':item['title'],'year':item['year'],'metadata_vector':entry['metadata_vector'],'creators':entry['creators']},'Comment':item['title']})
    call('/api/items',payload,'POST')
    conf=call('/api/dashboard/config')['recommend']
    conf['item_to_item']=[{'name':'genres','type':'tags','column':'item.Labels.genres'},{'name':'metadata','type':'embedding','column':'item.Labels.metadata_vector'},{'name':'creators','type':'tags','column':'item.Labels.creators'}]
    # JSON config uses kebab-case names for item-to-item; retain its existing spelling.
    conf['item-to-item']=conf.pop('item_to_item')
    conf['ranker']['recommenders']=['item-to-item/metadata']
    # The local relay blends creator/genre evidence with this content candidate source.
    conf['cache_size']=max(conf['cache_size'],256)
    for typ,key in [('recommend_like','positive_feedback_types'),('recommend_dislike','negative_feedback_types'),('recommend_watched','read_feedback_types')]:
        if not conf['data_source'].get(key):conf['data_source'][key]=[]
        if typ not in conf['data_source'][key]:conf['data_source'][key].append(typ)
    call('/api/dashboard/config',{'recommend':conf},'POST')
    print(json.dumps({'content_items':len(metadata),'creator_matches':sum(bool(m['creators']) for m in metadata.values()),'recommenders':conf['ranker']['recommenders']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--crew');a=p.parse_args();enrich_features(a.data,a.crew)
