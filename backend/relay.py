#!/usr/bin/env python3
"""LAN recommendation relay with public catalogue ingestion. Gorse itself remains on loopback.
Only the configured TV and this Mac may connect. No arbitrary proxy/admin routes.
"""
import re, argparse, json, urllib.request, urllib.error, threading, subprocess, sys, time, os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote
from personalize import catalogue

def recommendation_payload(data_dir):
    root=Path(data_dir)
    items=json.loads((root/'catalogue.json').read_text())
    matched=json.loads((root/'matches.json').read_text())
    profile=matched['profile']
    with urllib.request.urlopen('http://127.0.0.1:8088/api/recommend/'+quote(profile,safe='')+'/playable?n=48',timeout=8) as res:
        ids=json.load(res)
    seen=set(matched['seen']); seeds=matched['seeds']; seed_ids={s['item']['id'] for s in seeds}
    output=[]
    for item_id in ids:
        if item_id not in items or item_id in seen or item_id in seed_ids:continue
        item=dict(items[item_id]);genres=set(item['genres'])
        ranked=sorted(seeds,key=lambda s:len(genres.intersection(s['item']['genres']))/max(1,len(genres.union(s['item']['genres']))),reverse=True)
        if ranked:
            seed=ranked[0]; overlap=sorted(genres.intersection(seed['item']['genres']))
            if overlap:item['reason']='Similar genres to '+seed['item']['title']+' · '+', '.join(overlap[:2])
        output.append(item)
        if len(output)>=24:break
    return {'engine':'gorse','scope':'Amazon import · household profile unassigned',
            'seedCount':len(seeds),'catalogueCount':len(items),'items':output}

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

def handler(data_dir,allowed,sync=None):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.client_address[0] not in allowed:self.send_error(403);return
            if self.path!='/catalogue' or sync is None:self.send_error(404);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=100000:self.send_error(413);return
                added=sync.add(json.loads(self.rfile.read(length)))
            except (ValueError,OSError,TypeError):self.send_error(400);return
            body=json.dumps({'accepted':added}).encode();self.send_response(202)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.client_address[0] not in allowed:self.send_error(403);return
            if self.path not in ['/recommendations','/health']:self.send_error(404);return
            try:
                payload={'ready':True} if self.path=='/health' else recommendation_payload(data_dir)
                body=json.dumps(payload).encode();self.send_response(200)
            except (OSError,ValueError,KeyError,urllib.error.URLError):
                body=b'{"error":"Recommendation service is unavailable. Check Gorse on the Mac."}';self.send_response(503)
            self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass # no household history in request logs
    return Handler

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--db');p.add_argument('--tv-ip',required=True);p.add_argument('--bind',default='0.0.0.0');p.add_argument('--port',type=int,default=8766);a=p.parse_args()
    server=ThreadingHTTPServer((a.bind,a.port),handler(a.data,{'127.0.0.1',a.tv_ip},CatalogueSync(a.data,a.db) if a.db else None))
    print('TV recommendation relay on port '+str(a.port),flush=True);server.serve_forever()
if __name__=='__main__':main()
