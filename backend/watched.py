"""The one place that decides whether a profile has watched a FlixTor catalogue title or episode.

Data model. The importers record facts only, in each profile's matches.json under `viewing`:
which title, its IMDb id, seconds played, the furthest playback position the export states, and
for a series the same per episode. Nothing there says "finished". `assess()` turns those facts
into the two maps every reader uses, and nobody else recomputes them:
  titles    {catalogue id: {'watched': bool, 'source': SOURCE[, 'evidence': EVIDENCE]}}   (resolve())
  episodes  {catalogue series id: {SERVICE: {season: [episode, ...]}}}   finished episodes only
FlixTor's own playback position lives only on the TV, so the app layers it below these maps in
its `titleState()` / `episodeState()` functions.

Precedence is explicit, highest first (see PRECEDENCE):
  1. manual    the profile's own "Already watched" / "Not watched yet" / rating. Always wins.
  2. import    viewing recorded by a streaming service export (Netflix, Prime Video).

Imported viewing counts only when it is mostly finished, judged against the IMDb length by the
best evidence on record (see EVIDENCE):
  1. position  how far playback got. When the export states it, it alone decides: playing the
               first half twice is not finishing.
  2. duration  seconds played, used only when the export states no position.
A film is measured against its own runtime. An episode is measured against its own runtime, else
against the series' usual episode runtime (see LENGTHS). Unknown length means not decided.
A series title is never called watched from imported episodes; that needs a rule of its own.
An import can only say something was watched, never that it was not.
"""
import collections,json,re,sqlite3
from pathlib import Path
from history_index import norm

THRESHOLD=.8
PRECEDENCE=('manual','import')
SOURCES=('manual','netflix','amazon')
SERVICES=SOURCES[1:]
EVIDENCE=('position','duration')
LENGTHS=('episode','series')
CATALOGUE_ID=re.compile(r'flixtor:(?:tv|movie):\d{1,18}')
MOVIE_TYPES={'movie','tvMovie'}
SERIES_TYPES={'tvSeries','tvMiniSeries'}


def service(profile):
    """Which export a profile's matches.json came from. Netflix profiles carry their own id prefix."""
    return 'netflix' if isinstance(profile,str) and profile.startswith('ftv-netflix-') else 'amazon'


def key(item):
    return norm(str(item.get('title') or '')),item.get('type'),str(item.get('year') or '')


def number(value):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and value>0 else None


def metadata_id(item,features,recorded=None):
    """IMDb id of an imported or catalogue title, from facts already on record; never guessed."""
    ident=recorded or item.get('metadata_id') or (item['id'].split(':',2)[2] if item.get('id','').startswith('history:imdb:') else None)
    return ident or (features.get(item.get('id'),{}) or {}).get('source_id')


def viewings(matches):
    """A profile's viewing facts in one shape: item, metadata_id, seconds, position, episodes.
    A matches.json written before 2026-11-15 has no `viewing`; its seeds are mapped here, once."""
    rows=matches.get('viewing')
    if not isinstance(rows,list):
        rows=[dict(item=s.get('item'),seconds=s.get('recorded_seconds')) for s in matches.get('seeds',[]) if isinstance(s,dict)]
    out=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('item'),dict) or row['item'].get('type') not in {'movie','tv'}:continue
        episodes=[e for e in row.get('episodes') or [] if isinstance(e,(list,tuple)) and len(e)==4 and all(type(n) is int and n>0 for n in e[:2])]
        out.append(dict(item=row['item'],metadata_id=row.get('metadata_id'),seconds=number(row.get('seconds')),position=number(row.get('position')),
                        episodes=[(e[0],e[1],number(e[2]),number(e[3])) for e in episodes]))
    return out


def lengths(index,movies,series=()):
    """Lengths in seconds from the local IMDb index; absent means unknown.
    Returns ({movie id: seconds}, {series id: {'usual': seconds or None, (season, episode): seconds}})."""
    index=Path(index);movies=sorted({i for i in movies if i});series=sorted({i for i in series if i})
    if not (movies or series) or not index.exists():return {},{}
    db=sqlite3.connect('file:'+str(index)+'?mode=ro',uri=True)
    try:
        films={};shows={}
        for offset in range(0,len(movies),500):
            chunk=movies[offset:offset+500]
            for ident,kind,minutes in db.execute('select id,type,runtime from titles where id in (%s)'%','.join('?'*len(chunk)),chunk):
                if kind in MOVIE_TYPES and minutes:films[ident]=minutes*60
        listed=bool(db.execute("select 1 from sqlite_master where type='table' and name='episodes'").fetchone())
        for ident in series:
            row=db.execute('select type,runtime from titles where id=?',(ident,)).fetchone()
            if not row or row[0] not in SERIES_TYPES:continue
            found=collections.defaultdict(set)
            if listed:
                for season,episode,minutes in db.execute('select e.season,e.episode,t.runtime from episodes e join titles t on t.id=e.id where e.parent=?',(ident,)):
                    if season is not None and episode is not None and minutes:found[(season,episode)].add(minutes*60)
            # Two listings of one episode that disagree on length are not a fact.
            shows[ident]=dict({k:next(iter(v)) for k,v in found.items() if len(v)==1},usual=row[1]*60 if row[1] else None)
        return films,shows
    finally:db.close()


def finished(position,seconds,length):
    """The EVIDENCE that something `length` seconds long was mostly finished, or None."""
    if not length:return None
    if position:return 'position' if position>=THRESHOLD*length else None
    return 'duration' if seconds and seconds>=THRESHOLD*length else None


def assess(matches,catalogue,features,index):
    """Every imported "mostly finished" decision for one profile, with what it rested on.
    Returns dict(source, titles={catalogue id: evidence}, episodes={catalogue series id: {(season, episode): evidence}},
    report=counts of what was decided, by which evidence and length, and what could not be)."""
    rows=viewings(matches);report=collections.Counter()
    # A history-only title joins the catalogue on title, type and year, and only when that is
    # unique on both sides (the same rule the importers use for canonical matches).
    by_key={};ambiguous=set()
    for ident,item in catalogue.items():
        k=key(item)
        if k in by_key:ambiguous.add(k)
        by_key[k]=ident
    shared=collections.Counter(key(r['item']) for r in rows)
    def place(item):
        ident=item.get('id','')
        if ident not in catalogue:
            k=key(item)
            ident=None if k in ambiguous or shared[k]!=1 else by_key.get(k)
        return ident if ident and CATALOGUE_ID.fullmatch(ident) and catalogue[ident].get('type',item['type'])==item['type'] else None
    for row in rows:row['imdb']=metadata_id(row['item'],features,row['metadata_id']);row['place']=place(row['item'])
    films,shows=lengths(index,[r['imdb'] for r in rows if r['item']['type']=='movie'],[r['imdb'] for r in rows if r['item']['type']=='tv' and r['place'] and r['episodes']])
    titles={};episodes={}
    for row in rows:
        if row['item']['type']=='movie':
            report['films']+=1;length=films.get(row['imdb'])
            if not length:report['films length unknown']+=1;continue
            evidence=finished(row['position'],row['seconds'],length)
            if not evidence:report['films not finished']+=1;continue
            report['films finished by '+evidence]+=1
            if row['place']:titles[row['place']]=evidence
            else:report['films finished, not in catalogue']+=1
            continue
        report['episodes']+=len(row['episodes'])
        if not row['episodes']:continue
        if not row['place']:report['episodes of series not in catalogue']+=len(row['episodes']);continue
        known=shows.get(row['imdb'],{})
        for season,episode,seconds,position in row['episodes']:
            length=known.get((season,episode));basis='episode'
            if not length:length=known.get('usual');basis='series'
            if not length:report['episodes length unknown']+=1;continue
            evidence=finished(position,seconds,length)
            if not evidence:report['episodes not finished']+=1;continue
            report['episodes finished by '+evidence]+=1;report['episodes measured against '+basis+' length']+=1
            episodes.setdefault(row['place'],{})[(season,episode)]=evidence
    return dict(source=service(matches.get('profile')),titles=titles,episodes=episodes,report=dict(report))


def resolve(states,matches,catalogue,features,index,assessed=None):
    """states: FeedbackStore.states() for the profile. Returns the title map described above."""
    found=assessed or assess(matches,catalogue,features,index)
    layers={'manual':{ident:dict(watched=state['watched'],source='manual') for ident,state in states.items()
                      if isinstance(state.get('watched'),bool) and ident in catalogue and CATALOGUE_ID.fullmatch(ident)},
            'import':{ident:dict(watched=True,source=found['source'],evidence=evidence) for ident,evidence in found['titles'].items()}}
    out={}
    for layer in reversed(PRECEDENCE):out.update(layers[layer])
    return out


def imported_episodes(assessed):
    """The import layer of episode state: {catalogue series id: {SERVICE: {season: [episode, ...]}}}.
    The profile's own episode facts are kept apart (EpisodeProgressStore) and rank above this."""
    out={}
    for ident,found in assessed['episodes'].items():
        seasons=collections.defaultdict(list)
        for season,episode in sorted(found):seasons[season].append(episode)
        out[ident]={assessed['source']:{str(season):numbers for season,numbers in seasons.items()}}
    return out


def for_store(store,index):
    """Both maps for one profile's FeedbackStore (profile root + shared public catalogue root)."""
    public=store.catalogue_root
    def read(path,default):
        try:return json.loads(path.read_text()) if path.exists() else default
        except (OSError,ValueError):return default
    catalogue=read(public/'catalogue.json',{});features=read(store.root/'recommendation-features.json',{})
    if public!=store.root:features.update({k:v for k,v in read(public/'recommendation-features.json',{}).items() if k in catalogue})
    matches=read(store.root/'matches.json',{});found=assess(matches,catalogue,features,index)
    return dict(titles=resolve(store.states(),matches,catalogue,features,index,found),episodes=imported_episodes(found))
