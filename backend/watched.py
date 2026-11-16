"""The one place that decides whether a profile has watched a FlixTor catalogue title or episode.

Data model. The importers record facts only, in each profile's matches.json under `viewing`:
which title, its IMDb id, seconds played, the furthest playback position the export states, and
for a series the same per episode. Nothing there says "finished". `assess()` turns those facts
into the maps every reader uses, and nobody else recomputes them:
  titles    {catalogue id: {'watched': bool, 'source': SOURCE[, 'evidence': EVIDENCE]}}   (resolve())
  episodes  {catalogue series id: {SERVICE: {season: [episode, ...]}}}   finished episodes only
The catalogue holds only titles the TV has browsed so far. Finished titles it does not hold yet
are published by name instead (name_key(): type|title|year), so the TV can show them the first
time it meets them; once the catalogue learns such a title it moves to the maps above:
  named_titles    {SERVICE: [name key, ...]}
  named_episodes  {SERVICE: {name key: {season: [episode, ...]}}}
A name is offered only when it is unambiguous: a four-digit year, one viewed title of that name
for the profile, and no catalogue title of that name (so the two kinds of map never overlap).
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
import collections,json,re,sqlite3,threading,unicodedata
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


def name_key(item):
    """How a title is named when there is no catalogue id for it: type|title|year, or None.
    Must stay equal to FTV_HISTORY.nameKey in the app (src/watch-history.js); both tests share cases."""
    title=re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(item.get('title') or '')).lower());year=re.search(r'(?:19|20)\d{2}',str(item.get('year') or ''))
    return item['type']+'|'+title+'|'+year[0] if title and year and item.get('type') in {'movie','tv'} else None


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
    named_titles / named_episodes = the same keyed by name_key() for titles the catalogue does not hold,
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
    held={name_key(item) for item in catalogue.values() if isinstance(item,dict)};named=collections.Counter(name_key(r['item']) for r in rows)
    for row in rows:
        row['imdb']=metadata_id(row['item'],features,row['metadata_id']);row['place']=place(row['item']);name=name_key(row['item'])
        row['name']=name if name and not row['place'] and name not in held and named[name]==1 else None
    films,shows=lengths(index,[r['imdb'] for r in rows if r['item']['type']=='movie'],[r['imdb'] for r in rows if r['item']['type']=='tv' and (r['place'] or r['name']) and r['episodes']])
    titles={};episodes={};named_titles={};named_episodes={}
    for row in rows:
        if row['item']['type']=='movie':
            report['films']+=1;length=films.get(row['imdb'])
            if not length:report['films length unknown']+=1;continue
            evidence=finished(row['position'],row['seconds'],length)
            if not evidence:report['films not finished']+=1;continue
            report['films finished by '+evidence]+=1
            if row['place']:titles[row['place']]=evidence;continue
            report['films finished, not in catalogue']+=1
            if row['name']:named_titles[row['name']]=evidence;report['films finished, offered by name']+=1
            continue
        report['episodes']+=len(row['episodes'])
        if not row['episodes']:continue
        if not row['place']:report['episodes of series not in catalogue']+=len(row['episodes'])
        if not (row['place'] or row['name']):report['episodes of series with no usable name']+=len(row['episodes']);continue
        known=shows.get(row['imdb'],{})
        for season,episode,seconds,position in row['episodes']:
            length=known.get((season,episode));basis='episode'
            if not length:length=known.get('usual');basis='series'
            if not length:report['episodes length unknown']+=1;continue
            evidence=finished(position,seconds,length)
            if not evidence:report['episodes not finished']+=1;continue
            report['episodes finished by '+evidence]+=1;report['episodes measured against '+basis+' length']+=1
            if row['place']:episodes.setdefault(row['place'],{})[(season,episode)]=evidence
            else:named_episodes.setdefault(row['name'],{})[(season,episode)]=evidence;report['episodes finished, offered by name']+=1
    return dict(source=service(matches.get('profile')),titles=titles,episodes=episodes,named_titles=named_titles,named_episodes=named_episodes,report=dict(report))


def resolve(states,matches,catalogue,features,index,assessed=None):
    """states: FeedbackStore.states() for the profile. Returns the title map described above."""
    found=assessed or assess(matches,catalogue,features,index)
    layers={'manual':{ident:dict(watched=state['watched'],source='manual') for ident,state in states.items()
                      if isinstance(state.get('watched'),bool) and ident in catalogue and CATALOGUE_ID.fullmatch(ident)},
            'import':{ident:dict(watched=True,source=found['source'],evidence=evidence) for ident,evidence in found['titles'].items()}}
    out={}
    for layer in reversed(PRECEDENCE):out.update(layers[layer])
    return out


def by_season(found):
    seasons=collections.defaultdict(list)
    for season,episode in sorted(found):seasons[season].append(episode)
    return {str(season):numbers for season,numbers in seasons.items()}


def imported_episodes(assessed):
    """The import layer of episode state: {catalogue series id: {SERVICE: {season: [episode, ...]}}}.
    The profile's own episode facts are kept apart (EpisodeProgressStore) and rank above this."""
    return {ident:{assessed['source']:by_season(found)} for ident,found in assessed['episodes'].items()}


def named(assessed):
    """The import layers for titles the catalogue does not hold: (named_titles, named_episodes) as described above."""
    source=assessed['source'];titles=sorted(assessed['named_titles']);episodes={name:by_season(found) for name,found in sorted(assessed['named_episodes'].items())}
    return ({source:titles} if titles else {}),({source:episodes} if episodes else {})


ASSESSED={};ASSESSED_LOCK=threading.Lock()


def signature(paths):
    out=[]
    for path in paths:
        try:stat=path.stat();out.append((str(path),stat.st_mtime_ns,stat.st_size))
        except OSError:out.append((str(path),None,None))
    return tuple(out)


def for_store(store,index):
    """All four maps for one profile's FeedbackStore (profile root + shared public catalogue root).
    The import assessment is kept per profile and redone whenever one of the files it is built from
    changes (catalogue, features, matches, index). The profile's own choices are read fresh every time."""
    public=store.catalogue_root;index=Path(index)
    inputs=signature([public/'catalogue.json',store.root/'recommendation-features.json',public/'recommendation-features.json',store.root/'matches.json',index])
    with ASSESSED_LOCK:kept=ASSESSED.get(str(store.root))
    if not kept or kept[0]!=inputs:
        def read(path,default):
            try:return json.loads(path.read_text()) if path.exists() else default
            except (OSError,ValueError):return default
        catalogue=read(public/'catalogue.json',{});features=read(store.root/'recommendation-features.json',{})
        if public!=store.root:features.update({k:v for k,v in read(public/'recommendation-features.json',{}).items() if k in catalogue})
        kept=(inputs,assess(read(store.root/'matches.json',{}),catalogue,features,index),frozenset(catalogue))
        with ASSESSED_LOCK:ASSESSED[str(store.root)]=kept
    _,found,catalogue=kept;named_titles,named_episodes=named(found)
    return dict(titles=resolve(store.states(),None,catalogue,None,index,found),episodes=imported_episodes(found),named_titles=named_titles,named_episodes=named_episodes)
