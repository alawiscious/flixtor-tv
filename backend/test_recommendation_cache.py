"""Synthetic profile fixtures only; never connect to Gorse or private imports."""
import json
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from profiles import RecommendationProfiles
from relay import recommendation_payload


class RecommendationCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.public = self.base/'public'; self.directory = self.base/'profiles'
        self.public.mkdir(); self.directory.mkdir()
        self.ident = 'ftv-netflix-'+'a'*16
        self.named = self.directory/self.ident; self.named.mkdir()
        self.item = {'id': 'flixtor:tv:1', 'title': 'Example Story', 'year': '2025',
                     'type': 'tv', 'genres': ['Drama'], 'url': 'https://flixtor.to/watch/tv/1/example', 'image': ''}
        for root, profile in [(self.public, 'original-household'), (self.named, self.ident)]:
            (root/'matches.json').write_text(json.dumps({'profile': profile, 'seen': [], 'seeds': []}))
            (root/'catalogue.json').write_text(json.dumps({self.item['id']: self.item}))
        (self.directory/'profiles.json').write_text(json.dumps({'profiles': [{'id': self.ident, 'name': 'Example viewer'}]}))
        self.registry = RecommendationProfiles(self.public, self.directory)
        self.registry.snapshots.wait = .1
        self.addCleanup(self.finished)

    def finished(self):
        with self.registry.snapshots.condition:
            self.assertTrue(self.registry.snapshots.condition.wait_for(lambda: not self.registry.snapshots.running, 2))

    def rec(self, *_):
        return {'engine': 'gorse', 'items': [dict(self.item)], 'seedCount': 0}

    def test_shared_new_candidate_and_features_work_without_copying_private_inputs(self):
        new = dict(self.item, id='flixtor:tv:2', title='New public story')
        (self.public/'catalogue.json').write_text(json.dumps({new['id']: new}))
        (self.public/'recommendation-features.json').write_text(json.dumps({new['id']: {'rating': '8.5'}}))
        before = (self.named/'matches.json').read_bytes()
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock()
        response.read.return_value = json.dumps([new['id']]).encode()
        with patch('urllib.request.urlopen', return_value=response):
            result = recommendation_payload(self.named, self.registry.store(self.ident))
        self.assertEqual(result['catalogueCount'], 1)
        self.assertEqual(result['items'][0]['id'], new['id'])
        self.assertEqual(result['items'][0]['rating'], '8.5')
        with patch('feedback.gorse', return_value={}):
            self.registry.save({'profileId': self.ident, 'itemId': new['id'], 'preference': 'like'})
        progress = self.registry.save({'profileId': self.ident, 'action': 'episode_progress', 'operation': 'mark_range',
                                       'itemId': new['id'], 'completedSeasons': [1]})
        self.assertEqual(progress['completedSeasons'], [1])
        self.assertEqual((self.named/'matches.json').read_bytes(), before)
        self.assertNotIn(new['id'], json.loads((self.named/'catalogue.json').read_text()))
        self.assertEqual(self.registry.store().states(), {})

    def test_slow_household_does_not_block_healthy_named_profile_or_duplicate_jobs(self):
        gate = threading.Event(); calls = []
        def rec(root, store):
            calls.append(Path(root))
            if Path(root) == self.public: gate.wait(2)
            return self.rec()
        try:
            start = time.monotonic(); result = self.registry.bundle(rec)
            self.assertLess(time.monotonic()-start, .5)
            self.assertEqual(result['cacheStatus'], 'updating')
            self.assertEqual(len(result['profiles'][1]['items']), 1)
            self.registry.bundle(rec)
            self.assertEqual(calls.count(self.public), 1)
        finally:
            gate.set()

    def test_offline_uses_private_persisted_snapshots_with_status(self):
        self.registry.bundle(self.rec); self.finished()
        path = self.named/'recommendation-cache.json'
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        # Simulate relay restart and unavailable Gorse, with refresh due.
        self.registry = RecommendationProfiles(self.public, self.directory)
        self.registry.snapshots.refresh = 0
        def offline(*_): raise OSError('synthetic offline')
        self.registry.bundle(offline); self.finished()
        result = self.registry.bundle(offline)
        pack = result['profiles'][1]
        self.assertEqual(len(pack['items']), 1)
        self.assertTrue(pack['stale']); self.assertEqual(pack['cacheStatus'], 'stale')
        self.assertIsNotNone(pack['generatedAt']); self.assertIn('error', pack)

    def test_cached_disliked_watched_and_removed_titles_are_never_served(self):
        self.registry.bundle(self.rec); self.finished()
        with patch('feedback.gorse', side_effect=OSError('offline')):
            self.registry.save({'profileId': self.ident, 'itemId': self.item['id'], 'preference': 'dislike'})
        with patch('feedback.FeedbackStore.sync'):
            result = self.registry.bundle(self.rec)
            self.assertEqual(result['profiles'][1]['items'], [])
            self.finished()
        # Other viewer's facts never remove this household candidate.
        self.assertEqual(len(result['items']), 1)
        (self.public/'catalogue.json').write_text('{}')
        result = self.registry.bundle(self.rec)
        self.assertTrue(all(not pack['items'] for pack in result['profiles']))

    def test_input_hash_invalidates_on_public_features_and_private_matches(self):
        store = self.registry.store(self.ident); snapshots = self.registry.snapshots
        old = snapshots.key(self.named, store)
        (self.public/'recommendation-features.json').write_text('{"rating":1}')
        new = snapshots.key(self.named, store); self.assertNotEqual(old, new)
        # Same byte count still invalidates; file TTL/size alone is insufficient.
        (self.public/'recommendation-features.json').write_text('{"rating":2}')
        self.assertNotEqual(new, snapshots.key(self.named, store))
        (self.named/'matches.json').write_text(json.dumps({'profile': self.ident, 'seen': [self.item['id']], 'seeds': []}))
        self.assertNotEqual(new, snapshots.key(self.named, store))

    def test_copied_other_viewer_cache_is_rejected(self):
        self.registry.bundle(self.rec); self.finished()
        (self.named/'recommendation-cache.json').write_bytes((self.public/'recommendation-cache.json').read_bytes())
        self.registry = RecommendationProfiles(self.public, self.directory)
        def offline(*_): raise OSError('offline')
        result = self.registry.bundle(offline)
        self.assertEqual(result['profiles'][1]['items'], [])

    def test_new_watched_fact_or_imported_seen_fact_filters_saved_picks_immediately(self):
        self.registry.bundle(self.rec); self.finished()
        with patch('feedback.gorse', return_value={}):
            self.registry.save({'profileId': self.ident, 'itemId': self.item['id'], 'watched': True})
        gate = threading.Event()
        try:
            def slow(*_):
                gate.wait(2)
                return self.rec()
            result = self.registry.bundle(slow)
            self.assertEqual(result['profiles'][1]['items'], [])
            self.assertEqual(len(result['items']), 1)
            matches = json.loads((self.public/'matches.json').read_text())
            matches['seen'] = [self.item['id']]
            (self.public/'matches.json').write_text(json.dumps(matches))
            self.assertEqual(self.registry.bundle(slow)['items'], [])
        finally:
            gate.set()

    def test_corrupt_one_profile_inputs_do_not_remove_healthy_household(self):
        (self.named/'matches.json').write_text('[]')
        result = self.registry.bundle(self.rec)
        self.assertEqual(len(result['items']), 1)
        self.assertNotIn('profiles', result)  # malformed registry member omitted safely

    def test_failure_retry_is_cooled_down_per_input_version(self):
        calls = Mock(side_effect=OSError('offline'))
        self.registry.bundle(calls); self.finished()
        self.registry.bundle(calls); self.finished()
        self.assertEqual(calls.call_count, 2)  # one attempt per viewer, not per request


if __name__ == '__main__': unittest.main()
