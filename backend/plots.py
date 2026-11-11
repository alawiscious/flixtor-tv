"""Private public-synopsis cache keyed only by verified playable catalogue IDs."""
import json
import sqlite3
import time
import threading
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from pathlib import Path


class PlotStore:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'catalogue-plots.sqlite'
        self.automatic = {'enabled': False, 'state': 'disabled', 'saved': 0}
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
                'automatic': dict(self.automatic),
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


class _InformationPanel(HTMLParser):
    """Read text only; no scripts, resources, links or account fields are used."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = {'title': [], 'description': []}

    def handle_starttag(self, tag, attrs):
        classes = set(dict(attrs).get('class', '').split())
        kind = 'title' if 'poptitle' in classes else 'description' if {'d-flex', 'mt-1', 'mx-2', 't12'} <= classes else None
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, kind))
        if tag == 'br':
            self.handle_data(' ')

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        if any(tag in {'script', 'style'} for tag, _ in self.stack):
            return
        for kind in {kind for _, kind in self.stack if kind}:
            self.parts[kind].append(text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def public_plot(item):
    """Anonymous fixed-origin lookup. Never reuse the TV session or accept a URL."""
    match = re.fullmatch(r'flixtor:(movie|tv):(\d+)', item['id'])
    if not match:
        raise ValueError('Invalid playable identity')
    path = '/ajax/info/' + ('t' if match[1] == 'tv' else 'm') + '/' + match[2]
    request = urllib.request.Request('https://flixtor.to' + path, headers={
        'Accept': 'text/html', 'User-Agent': 'FlixTor-TV-Public-Synopsis/1'})
    # No environment proxy, redirect handler, cookie jar or credentials.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=4) as response:
            if response.status != 200 or response.headers.get_content_type() != 'text/html':
                return None
            body = response.read(65537)
            if len(body) > 65536:
                return None
    except urllib.error.HTTPError as error:
        error.close()
        return None
    panel = _InformationPanel()
    panel.feed(body.decode('utf-8', errors='replace'))
    title = ''.join(panel.parts['title'])
    key = lambda value: re.sub('[^a-z0-9]', '', value.lower())
    description = ' '.join(''.join(panel.parts['description']).split())
    if not key(title) or key(title) != key(item['title']):
        return None
    if not 40 <= len(description) <= 2000 or '<' in description or '>' in description:
        return None
    return dict(item, description=description)


class AutomaticPlotCollector:
    """Small independent passes; browsing/playback never waits for this worker.

    Missing/authenticated panels use the same one-hour retry deferral as manual
    collection. Only public catalogue identity goes to the fixed source; imported
    viewing history and inference stay on the Mac. Indexing remains shadow-only.
    """
    def __init__(self, store, indexer, fetch=public_plot, interval=300):
        self.store, self.indexer, self.fetch = store, indexer, fetch
        self.interval = interval
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.status('waiting')

    def status(self, state, **values):
        self.store.automatic = dict(self.store.automatic, enabled=True, state=state, **values)

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        self.stopped.set()

    def run(self):
        # Let startup and the first recommendation response finish first.
        if self.stopped.wait(5):
            return
        while not self.stopped.is_set():
            self.collect_once()
            if self.stopped.wait(self.interval):
                return

    def collect_once(self):
        if not self.lock.acquire(blocking=False):
            return
        saved = failed = 0
        try:
            batch = self.store.queue()['items'][:8]
            self.status('collecting' if batch else 'waiting')
            deadline = time.monotonic() + 40
            for item in batch:
                if self.stopped.is_set() or time.monotonic() + 5 > deadline:
                    break
                try:
                    row = self.fetch(item)
                except (OSError, ValueError):
                    row = None
                # Revalidate identity at save time: catalogue may change in flight.
                current = self.store.items().get(item['id'])
                if not current or (current['title'], current['year']) != (item['title'], item['year']):
                    continue
                result = self.store.save({'rows': [row]} if row else {'failed': [item['id']]})
                saved += result['saved']
                failed += result['failed']
                if self.stopped.wait(1):
                    break
            queue = self.store.queue()
            self.status('complete' if not queue['remaining'] else 'deferred' if not queue['items'] else 'waiting',
                        saved=saved, unavailable=failed)
        except (OSError, ValueError, KeyError, sqlite3.Error):
            # Do not expose source responses, titles, imported history or credentials.
            self.status('unavailable', saved=saved, unavailable=failed)
        finally:
            if saved:
                self.indexer.schedule()
            self.lock.release()


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
