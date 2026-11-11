#!/usr/bin/env python3
"""LAN recommendation relay with public catalogue ingestion. Gorse itself remains on loopback.
Only the configured TV and this Mac may connect. No arbitrary proxy/admin routes.
"""
import re, argparse, json, math, urllib.request, urllib.error, threading, subprocess, sys, time, os
from datetime import datetime,timezone
from feedback import FeedbackStore
from profiles import RecommendationProfiles
from plots import PlotStore,ShadowIndexer,AutomaticPlotCollector
from recommendation_features import vector
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote
from personalize import catalogue

def recommendation_payload(data_dir,feedback=None):
    root=Path(data_dir);items=json.loads((root/'catalogue.json').read_text());matched=json.loads((root/'matches.json').read_text())
    profile=matched['profile'];feedback=feedback or FeedbackStore(root);feedback.sync();states=feedback.states()
    with urllib.request.urlopen('http://127.0.0.1:8088/api/recommend/'+quote(profile,safe='')+'/playable?n=256',timeout=8) as res:ids=json.load(res)
    seen=set(matched['seen']);seeds=matched['seeds'];seed_ids={s['item']['id'] for s in seeds}
    feature_file=root/'recommendation-features.json';features=json.loads(feature_file.read_text()) if feature_file.exists() else {}
    now=datetime.now(timezone.utc);packs=[]
    for seed in seeds:
        item=seed['item'];weight=3 if seed.get('feedback_type')=='like' else .35 if 'watchlist' in seed.get('source','') else 1
        try:days=max(0,(now-datetime.fromisoformat(seed['at'].replace('Z','+00:00'))).days);weight*=.3+.7*math.exp(-days/730)
        except (ValueError,KeyError):pass
        packs.append((item,weight,features.get(item['id'],{})))
    for ident,state in states.items():
        if state['preference']=='like' and ident in items:packs.append((items[ident],4,features.get(ident,{})))
        if (state['watched'] is False or state['preference']=='like' and state['watched'] is not True) and ident in items and ident not in ids:ids.append(ident)
    def similarity(item,feature,seed,sf):
        x=set(item['genres']);y=set(seed['genres']);genre=len(x&y)/max(1,len(x|y))
        va=feature.get('metadata_vector') or vector(item);vb=sf.get('metadata_vector') or vector(seed)
        content=sum(a*b for a,b in zip(va,vb));a=set(feature.get('creators',[]));b=set(sf.get('creators',[]))
        creator=len(a&b)/max(1,len(a|b))
        return .45*genre+.35*content+.2*creator
    negatives=[items[ident] for ident,state in states.items() if state['preference']=='dislike' and ident in items]
    candidates=[]
    for rank,ident in enumerate(dict.fromkeys(ids)):
        if ident not in items:continue
        state=states.get(ident,{})
        if state.get('preference')=='dislike' or state.get('watched') is True:continue
        if state.get('watched') is not False and (ident in seen or ident in seed_ids):continue
        item=dict(items[ident]);feat=features.get(ident,{})
        scores=[(weight*similarity(item,feat,seed,sf),seed) for seed,weight,sf in packs]
        scores.sort(key=lambda pair:pair[0],reverse=True)
        score=sum(value for value,seed in scores[:8])/8 + .2/(1+rank/20)
        score-=.22*max((similarity(item,feat,negative,features.get(negative['id'],{})) for negative in negatives),default=0)
        if scores:
            seed=scores[0][1];item['reason']='Shares genres, era or creators with '+seed['title']
        else:item['reason']='Explore something from the catalogue'
        if state.get('watched') is False:item['reason']='You marked this as not watched · '+item['reason']
        item['feedback']=state;item['rating']=feat.get('rating','');candidates.append((score,item))
    output=[]
    while candidates and len(output)<24:
        best=max(range(len(candidates)),key=lambda n:candidates[n][0]-.24*max((similarity(candidates[n][1],features.get(candidates[n][1]['id'],{}),old,features.get(old['id'],{})) for old in output[-8:]),default=0))
        output.append(candidates.pop(best)[1])
    return {'engine':'gorse','scope':matched.get('scope','Amazon import · household profile unassigned'),'model':'Genres + content metadata + creators; explicit feedback, recency and diversity' if features else 'Genres + your feedback; recency and diversity',
            'seedCount':len(seeds),'catalogueCount':len(items),'items':output,'feedbackPending':sum(s['syncPending'] for s in states.values())}

class CatalogueSync:
    """Accept public card metadata, then match history locally. No raw history input."""
    def __init__(self,data_dir,db):
        self.root=Path(data_dir);self.db=db;self.lock=threading.Lock();self.pending={};self.scheduled=False
    def add(self,rows):
        if not isinstance(rows,list) or len(rows)>160:raise ValueError('Invalid catalogue')
        valid=[]
        for row in rows:
            if not isinstance(row,list) or len(row)!=5 or not all(isinstance(v,str) and len(v)<=500 for v in row):continue
            url,title,year,genres,image=row
            if not re.fullmatch(r'/watch/(?:movie|tv)/\d+/[a-z0-9-]+',url):continue
            if not re.fullmatch(r'(19|20)\d{2}',year):continue
            if not re.fullmatch(r'[A-Za-z ,&-]{1,150}',genres):continue
            if not re.fullmatch(r'https://img\.xcdn\.to/t/p/w\d+/[A-Za-z0-9]+\.jpg',image):continue
            valid.append(row)
        additions=catalogue(valid)
        with self.lock:
            known=json.loads((self.root/'catalogue.json').read_text())
            additions={k:v for k,v in additions.items() if k not in known}
            self.pending.update(additions)
            if self.pending and not self.scheduled:
                self.scheduled=True
                timer=threading.Timer(3,self.run);timer.daemon=True;timer.start()
        return len(additions)
    def run(self):
        try:
            with self.lock:
                items=json.loads((self.root/'catalogue.json').read_text());items.update(self.pending);self.pending={}
            rows=[[i['url'].replace('https://flixtor.to',''),i['title'],i['year'],i['meta'],i['image']] for i in items.values()]
            path=self.root/'expanded_catalogue.json';path.write_text(json.dumps(rows))
            # Local trusted code only; never form a command from request parameters.
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('personalize.py')),'--db',self.db,'--catalogue',str(path),'--out',str(self.root),'--apply'],capture_output=True,timeout=90)
            if result.returncode:print('Catalogue refresh failed; existing recommendations remain available.',flush=True)
            else:print('Catalogue refreshed from public TV cards.',flush=True)
        finally:
            with self.lock:
                self.scheduled=False
                if self.pending:
                    self.scheduled=True;timer=threading.Timer(3,self.run);timer.daemon=True;timer.start()

def handler(data_dir,allowed,sync=None,automatic_plots=False):
    profiles=RecommendationProfiles(data_dir)
    plots=PlotStore(data_dir)
    indexer=ShadowIndexer(data_dir,sync.db if sync else None)
    collector=AutomaticPlotCollector(plots,indexer) if automatic_plots else None
    if collector:collector.start()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.client_address[0] not in allowed:self.send_error(403);return
            if self.path not in ['/catalogue','/feedback','/plots'] or (self.path=='/catalogue' and sync is None):self.send_error(404);return
            origin=self.headers.get('Origin')
            if origin and not re.fullmatch(r'http://(?:127\.0\.0\.1|localhost):(?:8765|8770|8771)',origin):self.send_error(403);return
            if self.headers.get_content_type()!='application/json':self.send_error(415);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=100000:self.send_error(413);return
                payload=json.loads(self.rfile.read(length))
                result=plots.save(payload) if self.path=='/plots' else {'accepted':sync.add(payload)} if self.path=='/catalogue' else {'saved':True,'state':profiles.save(payload)}
                if self.path=='/plots' and result['saved']:indexer.schedule()
            except (ValueError,OSError,TypeError):self.send_error(400);return
            body=json.dumps(result).encode();self.send_response(202 if self.path=='/catalogue' else 200)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.client_address[0] not in allowed:self.send_error(403);return
            if self.path not in ['/recommendations','/health','/plots']:self.send_error(404);return
            try:
                payload={'ready':True} if self.path=='/health' else plots.queue() if self.path=='/plots' else profiles.bundle(recommendation_payload)
                body=json.dumps(payload).encode();self.send_response(200)
            except (OSError,ValueError,KeyError,urllib.error.URLError):
                body=b'{"error":"Recommendation service is unavailable. Check Gorse on the Mac."}';self.send_response(503)
            self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass # no household history in request logs
    Handler.plot_collector=collector
    return Handler

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--db');p.add_argument('--tv-ip',required=True);p.add_argument('--bind',default='0.0.0.0');p.add_argument('--port',type=int,default=8772);a=p.parse_args()
    routes=handler(a.data,{'127.0.0.1',a.tv_ip},CatalogueSync(a.data,a.db) if a.db else None,automatic_plots=True)
    server=ThreadingHTTPServer((a.bind,a.port),routes)
    try:
        print('TV recommendation relay on port '+str(a.port),flush=True);server.serve_forever()
    finally:
        if routes.plot_collector:routes.plot_collector.stop()
        server.server_close()
if __name__=='__main__':main()
