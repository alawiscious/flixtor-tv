import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semantic_index import build, descriptions, normalize


class SemanticIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.item = {'id': 'movie:1', 'title': 'Example', 'type': 'movie',
                     'description': 'A stranded scientist must find a way home across an alien planet.'}
        (self.root / 'catalogue.json').write_text(json.dumps({'movie:1': self.item, 'movie:2': {'id': 'movie:2', 'title': 'No plot', 'type': 'movie'}}))
        (self.root / 'matches.json').write_text(json.dumps({'seeds': [], 'seen': []}))

    def test_missing_plots_are_excluded_and_coverage_is_honest(self):
        report = build(self.root, prepare_only=True)
        self.assertEqual((report['documents'], report['unseen_playable_plots'], report['unseen_playable_total']), (1, 1, 2))
        self.assertFalse((self.root / 'semantic-shadow.json').exists())
        self.assertFalse(report['serving_changed'])

    def test_model_failure_records_blocker_without_touching_live_features(self):
        live = self.root / 'recommendation-features.json'
        live.write_text('unchanged')
        with patch('semantic_index.local_call', side_effect=OSError('offline')):
            self.assertEqual(build(self.root)['status'], 'blocked')
        self.assertEqual(live.read_text(), 'unchanged')

    def test_cache_is_invalidated_when_model_digest_changes(self):
        def response(path, payload=None):
            return {'models': [{'name': 'nomic-embed-text:v1.5', 'digest': 'new'}]} if path == '/api/tags' else {'embeddings': [[3, 4]]}
        with patch('semantic_index.local_call', side_effect=response) as call:
            self.assertEqual(build(self.root)['embedded'], 1)
            self.assertEqual(call.call_count, 2)
        with patch('semantic_index.local_call', side_effect=response) as call:
            build(self.root)
            self.assertEqual(call.call_count, 1)
        cache = self.root / 'semantic-shadow.json'
        value = json.loads(cache.read_text()); value['model_digest'] = 'old'; cache.write_text(json.dumps(value))
        with patch('semantic_index.local_call', side_effect=response) as call:
            build(self.root)
            self.assertEqual(call.call_count, 2)

    def test_ambiguous_source_mapping_is_not_used(self):
        db_path = self.root / 'amazon.sqlite'
        db = sqlite3.connect(db_path)
        for table in ['items', 'watch_summaries']:
            db.execute('create table ' + table + ' (item_id text,title text,description text)')
        db.execute('insert into items values (?,?,?)', ('source', 'No plot', self.item['description']))
        db.commit(); db.close()
        review = [{'source_id': 'source', 'source_title': 'No plot', 'canonical_id': ident} for ident in ['movie:1', 'movie:2']]
        (self.root / 'metadata_mapping_review.json').write_text(json.dumps(review))
        docs, *_ = descriptions(self.root, db_path)
        self.assertNotIn('movie:2', docs)
        (self.root / 'metadata_mapping_review.json').write_text(json.dumps(review[1:]))
        docs, *_ = descriptions(self.root, db_path)
        self.assertEqual(docs['movie:2']['source'], 'Amazon movie description')

    def test_invalid_vectors_are_rejected(self):
        for vector in [[], [0, 0], [math.nan], [math.inf], [True], ['1']]:
            with self.assertRaises(ValueError): normalize(vector)
        self.assertAlmostEqual(sum(v*v for v in normalize([3, 4])), 1)


if __name__ == '__main__':
    unittest.main()
