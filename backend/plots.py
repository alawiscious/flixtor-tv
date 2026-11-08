"""Private public-synopsis cache keyed only by verified playable catalogue IDs."""
import json
import sqlite3
import time
import threading
from pathlib import Path


class PlotStore:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'catalogue-plots.sqlite'
        db = self.connect()
        try:
            with db:
                db.execute('create table if not exists plots (id text primary key,title text,year text,description text,updated real)')
                db.execute('create table if not exists attempts (id text primary key,at real)')
        finally:
            db.close()

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def items(self):
        return json.loads((self.root / 'catalogue.json').read_text())

    def queue(self):
        items = self.items()
        db = self.connect()
        try:
            plots = {ident: (title, year) for ident, title, year in db.execute('select id,title,year from plots')}
            recent = {ident for ident, in db.execute('select id from attempts where at>?', (time.time()-3600,))}
        finally:
            db.close()
        missing = [item for ident, item in items.items() if plots.get(ident) != (item['title'], item['year'])]
        eligible = [item for item in missing if item['id'] not in recent]
        return {'total': len(items), 'collected': len(items)-len(missing), 'remaining': len(missing),
                'deferred': len(missing)-len(eligible),
                'items': [{key: item[key] for key in ['id', 'title', 'year']} for item in eligible[:32]]}

    def save(self, payload):
        if not isinstance(payload, dict) or set(payload)-{'rows', 'failed'}:
            raise ValueError('Invalid synopsis batch')
        rows, failed = payload.get('rows', []), payload.get('failed', [])
        if not isinstance(rows, list) or not isinstance(failed, list) or len(rows)+len(failed)>32:
            raise ValueError('Invalid synopsis batch size')
        items = self.items()
        valid = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {'id', 'title', 'year', 'description'}:
                raise ValueError('Invalid synopsis fields')
            if not all(isinstance(v, str) for v in row.values()):
                raise ValueError('Invalid synopsis types')
            item = items.get(row['id'])
            if not item or row['title'] != item['title'] or row['year'] != item['year']:
                raise ValueError('Unknown or changed title identity')
            description = ' '.join(row['description'].split())
            if not 40 <= len(description) <= 2000 or '<' in description or '>' in description:
                raise ValueError('Invalid synopsis text')
            valid.append((row['id'], item['title'], item['year'], description, time.time()))
        if any(not isinstance(ident, str) or ident not in items for ident in failed):
            raise ValueError('Unknown failed title')
        db = self.connect()
        try:
            with db:
                db.executemany('insert or replace into plots values (?,?,?,?,?)', valid)
                db.executemany('insert or replace into attempts values (?,?)', [(ident, time.time()) for ident in failed])
        finally:
            db.close()
        return {'saved': len(valid), 'failed': len(failed), 'coverage': self.queue()}


class ShadowIndexer:
    """Coalesce incoming batches into one local inference job at a time."""
    def __init__(self, root, db_path):
        self.root, self.db_path = root, db_path
        self.lock = threading.Lock()
        self.running = self.dirty = False

    def schedule(self):
        with self.lock:
            self.dirty = True
            if self.running:
                return
            self.running = True
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        from semantic_index import build
        try:
            while True:
                with self.lock:
                    self.dirty = False
                build(self.root, self.db_path)
                with self.lock:
                    if not self.dirty:
                        self.running = False
                        return
        except Exception:
            # No model input/history in relay logs. The next batch can retry.
            with self.lock:
                self.running = False
            print('Story index update failed; existing recommendations remain available.', flush=True)
