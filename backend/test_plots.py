import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plots import PlotStore
from semantic_index import descriptions


class PlotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.item = {'id': 'flixtor:movie:123', 'title': 'Example', 'year': '2025', 'type': 'movie'}
        self.write_catalogue(self.item)
        (self.root / 'matches.json').write_text(json.dumps({'seeds': [], 'seen': []}))
        self.store = PlotStore(self.root)
        self.row = dict(self.item, description='A stranded scientist must find a route home across an alien planet.')
        del self.row['type']

    def write_catalogue(self, item):
        (self.root / 'catalogue.json').write_text(json.dumps({item['id']: item}))

    def test_saved_plots_survive_catalogue_rebuild_and_feed_index(self):
        self.assertEqual(len(self.store.queue()['items']), 1)
        self.store.save({'rows': [self.row]})
        self.write_catalogue(self.item)
        self.assertEqual(self.store.queue()['collected'], 1)
        docs, *_ = descriptions(self.root)
        self.assertEqual(docs[self.item['id']]['source'], 'FlixTor information popup')
        self.assertIn('stranded scientist', docs[self.item['id']]['input'])

    def test_mismatched_identity_rejected_and_changed_catalogue_requeues(self):
        with self.assertRaises(ValueError): self.store.save({'rows': [dict(self.row, title='Different film')]})
        with self.assertRaises(ValueError): self.store.save({'rows': [dict(self.row, id='history:imdb:tt123')]})
        self.store.save({'rows': [self.row]})
        self.write_catalogue(dict(self.item, year='2026'))
        self.assertEqual(self.store.queue()['remaining'], 1)
        self.assertEqual(descriptions(self.root)[0], {})

    def test_failures_are_deferred_without_counting_as_collected(self):
        with patch('plots.time.time', return_value=10000):
            self.store.save({'failed': [self.item['id']]})
            status = self.store.queue()
            self.assertEqual((status['remaining'], status['collected'], status['deferred']), (1, 0, 1))
            self.assertEqual(status['items'], [])
        with patch('plots.time.time', return_value=14000):
            self.assertEqual(len(self.store.queue()['items']), 1)

    def test_batch_is_atomic_when_later_row_invalid(self):
        with self.assertRaises(ValueError): self.store.save({'rows': [self.row, dict(self.row, description='<script>oops</script>')]})
        self.assertEqual(self.store.queue()['collected'], 0)
        for payload in [{'rows': [self.row]*33}, {'failed': ['unknown']}, {'rows': [dict(self.row, cookie='secret')]}]:
            with self.assertRaises(ValueError): self.store.save(payload)


if __name__ == '__main__': unittest.main()
