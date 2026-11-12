"""Private, input-versioned snapshots; no network work on the response thread."""
import hashlib
import json
import os
import threading
import time
import sqlite3
import math
import tempfile
from datetime import datetime, timezone


class RecommendationSnapshots:
    VERSION = 'shared-public-catalogue-v1'

    def __init__(self, public_root, wait=1.5, refresh=60):
        self.public_root = public_root
        self.wait, self.refresh = wait, refresh
        self.condition = threading.Condition()
        self.running, self.memory, self.errors, self.attempts = set(), {}, {}, {}

    def key(self, root, store):
        digest = hashlib.sha256((self.VERSION + datetime.now(timezone.utc).date().isoformat()).encode())
        paths = [self.public_root/'catalogue.json', self.public_root/'recommendation-features.json',
                 root/'matches.json', root/'recommendation-features.json']
        for path in paths:
            digest.update(str(path).encode())
            digest.update(path.read_bytes() if path.exists() else b'absent')
        digest.update(json.dumps(store.states(), sort_keys=True).encode())
        return digest.hexdigest()

    def load(self, entry):
        ident = entry['id']
        if ident not in self.memory:
            try:
                snapshot = json.loads((entry['root']/'recommendation-cache.json').read_text())
                if (snapshot.get('profileId') != ident
                        or snapshot.get('sourceProfile') != json.loads((entry['root']/'matches.json').read_text())['profile']
                        or not isinstance(snapshot['key'], str)
                        or not isinstance(snapshot['at'], (int, float)) or not math.isfinite(snapshot['at'])
                        or not 0 <= snapshot['at'] <= time.time()+300
                        or not isinstance(snapshot['pack']['items'], list)
                        or not all(isinstance(item, dict) for item in snapshot['pack']['items'])):
                    raise ValueError('Invalid snapshot')
                self.memory[ident] = snapshot
            except (OSError, ValueError, KeyError, TypeError):
                self.memory[ident] = None
        return self.memory[ident]

    def fresh(self, snapshot, key):
        return snapshot and snapshot['key'] == key and 0 <= time.time()-snapshot['at'] < self.refresh

    def launch(self, entry, store, recommend, key):
        ident = entry['id']
        if ident in self.running:
            return
        previous = self.attempts.get(ident)
        if previous and previous[0] == key and ident in self.errors and time.monotonic()-previous[1] < 30:
            return
        self.attempts[ident] = (key, time.monotonic())
        self.running.add(ident)
        def job():
            try:
                pack = recommend(entry['root'], store)
                if self.key(entry['root'], store) != key:
                    return
                snapshot = {'profileId': ident, 'sourceProfile': store.profile(), 'key': key, 'at': time.time(), 'pack': pack}
                path = entry['root']/'recommendation-cache.json'
                # Create private before writing; atomic replacement preserves last good cache.
                with tempfile.NamedTemporaryFile(mode='w', dir=entry['root'], prefix='.recommendation-', delete=False) as output:
                    temporary = type(path)(output.name)
                    try:
                        os.chmod(temporary, 0o600)
                        json.dump(snapshot, output)
                        output.close()
                        temporary.replace(path)
                    finally:
                        temporary.unlink(missing_ok=True)
                with self.condition:
                    self.memory[ident] = snapshot
                    self.errors.pop(ident, None)
                    self.condition.notify_all()
                # Outbox retries are background work, never part of HTTP response latency.
                if any(state.get('syncPending') for state in store.states().values()):
                    store.sync()
            except Exception:
                with self.condition:
                    self.errors[ident] = 'Recommendations unavailable; saved picks may be out of date'
            finally:
                with self.condition:
                    self.running.discard(ident)
                    self.condition.notify_all()
        threading.Thread(target=job, daemon=True).start()

    def safe_pack(self, entry, store, snapshot, key):
        if snapshot is None:
            return {'engine': 'gorse', 'items': [], 'seedCount': 0,
                    'error': self.errors.get(entry['id'], 'Recommendations are updating' if entry['id'] in self.running else 'Recommendations unavailable'),
                    'stale': True, 'cacheStatus': 'updating' if entry['id'] in self.running else 'unavailable',
                    'generatedAt': None}
        pack = dict(snapshot['pack'])
        # Feedback and removals take precedence immediately, including during outages.
        items = json.loads((self.public_root/'catalogue.json').read_text())
        matches = json.loads((entry['root']/'matches.json').read_text())
        if snapshot['sourceProfile'] != matches['profile']:
            return self.safe_pack(entry, store, None, key)
        states = store.states()
        seen = set(matches.get('seen', [])) | {s['item']['id'] for s in matches.get('seeds', [])}
        safe = []
        for old in pack.get('items', []):
            ident = old.get('id')
            if ident not in items:
                continue
            state = states.get(ident, {})
            if state.get('watched') is True or state.get('preference') == 'dislike':
                continue
            if ident in seen and state.get('watched') is not False:
                continue
            safe.append(dict(old, **items[ident], feedback=state))
        stale = not self.fresh(snapshot, self.key(entry['root'], store)) or entry['id'] in self.errors
        pack.update(items=safe, stale=stale, cacheStatus='stale' if stale else 'fresh',
                    generatedAt=datetime.fromtimestamp(snapshot['at'], timezone.utc).isoformat(),
                    feedbackPending=sum(bool(state.get('syncPending')) for state in states.values()))
        if entry['id'] in self.errors:
            pack['error'] = self.errors[entry['id']]
        return pack

    def bundle(self, entries, get_store, recommend):
        pending = []
        with self.condition:
            for entry in entries:
                try:
                    store = get_store(entry['id'])
                    key = self.key(entry['root'], store)
                    snapshot = self.load(entry)
                    if not self.fresh(snapshot, key):
                        self.launch(entry, store, recommend, key)
                    pending.append((entry, store, key))
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                    self.errors[entry['id']] = 'Profile recommendation inputs unavailable'
                    pending.append((entry, None, None))
            # Warm/stale snapshots return immediately; only cold profiles use the bounded wait.
            deadline = time.monotonic() + self.wait
            while any(not self.memory.get(e['id']) and e['id'] in self.running for e, _, _ in pending):
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            packs = []
            for entry, store, key in pending:
                try:
                    packs.append(self.safe_pack(entry, store, self.memory.get(entry['id']) if store else None, key))
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                    packs.append(self.safe_pack(entry, store, None, key))
            return packs
