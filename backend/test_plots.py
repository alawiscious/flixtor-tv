import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import urllib.error

from plots import PlotStore, AutomaticPlotCollector, public_plot, _NoRedirect
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

    def collector(self, fetch):
        indexer = Mock()
        collector = AutomaticPlotCollector(self.store, indexer, fetch=fetch)
        # Synthetic passes have no wall-clock waits or network requests.
        collector.stopped = Mock()
        collector.stopped.is_set.return_value = False
        collector.stopped.wait.return_value = False
        return collector, indexer

    def test_automatic_pass_is_bounded_and_indexes_once(self):
        items = {str(n): dict(self.item, id='flixtor:movie:'+str(n)) for n in range(20)}
        (self.root/'catalogue.json').write_text(json.dumps({i['id']: i for i in items.values()}))
        fetch = Mock(side_effect=lambda item: dict(item, description=self.row['description']))
        collector, indexer = self.collector(fetch)
        collector.collect_once()
        self.assertEqual(fetch.call_count, 8)
        self.assertEqual(self.store.queue()['collected'], 8)
        self.assertEqual(self.store.queue()['automatic']['state'], 'waiting')
        indexer.schedule.assert_called_once_with()

    def test_automatic_auth_failure_defers_without_removing_saved_plots(self):
        error = urllib.error.HTTPError('https://flixtor.to', 403, 'Forbidden', {}, None)
        self.addCleanup(error.close)
        collector, indexer = self.collector(Mock(side_effect=error))
        collector.collect_once()
        status = self.store.queue()
        self.assertEqual((status['collected'], status['deferred']), (0, 1))
        self.assertEqual(status['automatic']['state'], 'deferred')
        self.assertEqual(status['automatic']['unavailable'], 1)
        indexer.schedule.assert_not_called()
        collector.collect_once()
        self.assertEqual(collector.fetch.call_count, 1)

    def test_automatic_changed_identity_cannot_save_stale_response(self):
        def fetch(item):
            self.write_catalogue(dict(self.item, year='2026'))
            return self.row
        collector, indexer = self.collector(fetch)
        collector.collect_once()
        self.assertEqual(self.store.queue()['collected'], 0)
        self.assertEqual(self.store.queue()['deferred'], 0)
        indexer.schedule.assert_not_called()

    def test_automatic_stopped_or_overlapping_pass_performs_no_fetch(self):
        collector, indexer = self.collector(Mock())
        collector.stopped.is_set.return_value = True
        collector.collect_once()
        collector.stopped.is_set.return_value = False
        collector.lock.acquire()
        try:
            collector.collect_once()
        finally:
            collector.lock.release()
        collector.fetch.assert_not_called()
        indexer.schedule.assert_not_called()

    def test_automatic_complete_cache_performs_no_network(self):
        self.store.save({'rows': [self.row]})
        collector, indexer = self.collector(Mock())
        collector.collect_once()
        collector.fetch.assert_not_called()
        self.assertEqual(self.store.queue()['automatic']['state'], 'complete')

    def test_worker_waits_between_passes_including_unavailable_sources(self):
        collector, _ = self.collector(Mock())
        collector.collect_once = Mock()
        collector.stopped.wait.side_effect = [False, True]
        collector.run()
        collector.collect_once.assert_called_once_with()
        self.assertEqual([c.args[0] for c in collector.stopped.wait.call_args_list], [5, 300])

    def test_pass_does_not_start_a_request_without_remaining_time_budget(self):
        collector, indexer = self.collector(Mock())
        with patch('plots.time.monotonic', side_effect=[0, 36]):
            collector.collect_once()
        collector.fetch.assert_not_called()
        indexer.schedule.assert_not_called()

    def response(self, body, content_type='text/html'):
        response = Mock()
        response.status = 200
        response.headers.get_content_type.return_value = content_type
        response.read.return_value = body.encode()
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_anonymous_lookup_uses_numeric_fixed_endpoint_and_text_only(self):
        body = '<div class="poptitle">Example</div><div class="d-flex mt-1 mx-2 t12">A stranded <b>scientist</b><script>secret</script> must find a route home across an alien planet.</div>'
        opener = Mock()
        opener.open.return_value = self.response(body)
        with patch('plots.urllib.request.build_opener', return_value=opener) as build:
            row = public_plot({k: self.item[k] for k in ('id', 'title', 'year')})
        self.assertEqual(row, self.row)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://flixtor.to/ajax/info/m/123')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 4)
        self.assertFalse(any(k.lower() in {'cookie', 'authorization'} for k in request.headers))
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsNone(_NoRedirect().redirect_request(None, None, None, None, None, None))

    def test_anonymous_lookup_rejects_wrong_identity_nonhtml_and_oversized_response(self):
        for body, kind in [('<div class="poptitle">Other Film</div>', 'text/html'),
                           ('<div class="poptitle">Example</div>', 'application/json'),
                           ('x'*65537, 'text/html')]:
            opener = Mock()
            opener.open.return_value = self.response(body, kind)
            with patch('plots.urllib.request.build_opener', return_value=opener):
                self.assertIsNone(public_plot(self.item))
        with self.assertRaises(ValueError):
            public_plot(dict(self.item, id='https://evil.example/movie/123'))


if __name__ == '__main__': unittest.main()
