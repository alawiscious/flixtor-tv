"""Public (Funnel) listener: device tokens, pairing, profile isolation. Synthetic data, real HTTP."""
import io, json, os, stat, tempfile, threading, time, unittest, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import relay
from devices import DeviceRegistry, DeviceError, CODE_TTL
import pair_device


class Clock:
    def __init__(self): self.now = time.time()  # starts at real time so the CLI's codes agree
    def __call__(self): return self.now


def fake_recommend(root, store):
    return {'engine': 'gorse', 'items': [{'id': 'flixtor:movie:1', 'reason': 'synthetic'}], 'scope': store.profile(), 'seedCount': 1}


class RemoteAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); base = Path(self.temp.name)
        # Layout mirrors production: <imports>/amazon/personalized + <imports>/netflix/profiles.
        self.default = base/'amazon/personalized'; self.directory = base/'netflix/profiles'
        self.default.mkdir(parents=True); self.directory.mkdir(parents=True)
        self.ids = ['ftv-netflix-'+'a'*16, 'ftv-netflix-'+'b'*16]
        item = {'id': 'flixtor:movie:1', 'title': 'Synthetic pick', 'url': 'https://flixtor.to/watch/movie/1/synthetic', 'image': 'https://img.xcdn.to/t/p/w342/a.jpg', 'genres': []}
        for root, ident in [(self.default, 'household-src')]+[(self.directory/i, i) for i in self.ids]:
            root.mkdir(exist_ok=True); (root/'matches.json').write_text(json.dumps({'profile': ident, 'seen': [], 'seeds': []}))
        (self.default/'catalogue.json').write_text(json.dumps({'flixtor:movie:1': item}))
        (self.directory/'profiles.json').write_text(json.dumps({'profiles': [{'id': self.ids[0], 'name': 'Viewer One'}, {'id': self.ids[1], 'name': 'Viewer Two'}]}))
        self.patches = [patch('feedback.gorse', return_value={}), patch('relay.recommendation_payload', fake_recommend)]
        for p in self.patches: p.start()
        self.clock = Clock(); self.devices_path = base/'remote/devices.json'
        self.registry = DeviceRegistry(self.devices_path, clock=self.clock)
        self.services = relay.Services(str(self.default))
        self.public = self.serve(relay.public_handler(self.services, self.registry, request_limit=50, pair_limit=50))
        self.lan = self.serve(relay.handler(str(self.default), {'127.0.0.1'}, services=self.services))

    def serve(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:%d' % server.server_address[1]

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def call(self, base, path, body=None, token=None, headers=None):
        h = dict(headers or {})
        if token: h['Authorization'] = 'Bearer '+token
        if body is not None: h['Content-Type'] = 'application/json'
        req = urllib.request.Request(base+path, data=None if body is None else json.dumps(body).encode(), headers=h, method='POST' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=5) as r: return r.status, r.read().decode()
        except urllib.error.HTTPError as e: return e.code, e.read().decode()

    def pair(self, label='Remote TV', profiles=None, replace=False):
        code = self.registry.create(label, profiles or [self.ids[0]], replace=replace)
        status, body = self.call(self.public, '/pair', {'code': code})
        self.assertEqual(status, 200, body)
        return json.loads(body)['token']

    # --- authorization -------------------------------------------------------------------
    def test_requests_without_valid_token_are_refused_even_from_loopback(self):
        # The test client is 127.0.0.1, exactly what Funnel traffic looks like. The LAN listener trusts
        # that address; the public listener must not.
        self.assertEqual(self.call(self.lan, '/recommendations')[0], 200)
        for token, headers in [(None, None), ('x'*43, None), (None, {'Authorization': 'Basic abc'}), (None, {'Authorization': 'Bearer short'})]:
            for path in ['/recommendations', '/device']:
                status, body = self.call(self.public, path, token=token, headers=headers)
                self.assertEqual(status, 401, path); self.assertEqual(json.loads(body)['code'], 'unpaired')
            self.assertEqual(self.call(self.public, '/feedback', {'profileId': self.ids[0], 'itemId': 'flixtor:movie:1', 'preference': 'like'}, token=token, headers=headers)[0], 401)

    def test_health_is_open_and_minimal_plots_and_browsers_are_refused(self):
        self.assertEqual(self.call(self.public, '/health'), (200, '{"ready": true}'))
        token = self.pair()
        self.assertEqual(self.call(self.public, '/plots', token=token)[0], 404)
        self.assertEqual(self.call(self.public, '/plots', [], token=token)[0], 404)
        self.assertEqual(self.call(self.public, '/recommendations', token=token, headers={'Origin': 'https://evil.example'})[0], 403)

    # --- pairing -------------------------------------------------------------------------
    def test_pairing_code_is_single_use_normalized_and_expires(self):
        code = self.registry.create('Remote TV', [self.ids[0]])
        status, body = self.call(self.public, '/pair', {'code': (code[:4]+'-'+code[4:]).lower()})
        self.assertEqual(status, 200); paired = json.loads(body)
        self.assertEqual(paired['profiles'], [{'id': self.ids[0], 'name': 'Viewer One'}]); self.assertGreaterEqual(len(paired['token']), 40)
        self.assertEqual(self.call(self.public, '/pair', {'code': code})[0], 401, 'second use')
        late = self.registry.create('Late TV', [self.ids[0]]); self.clock.now += CODE_TTL+1
        self.assertEqual(self.call(self.public, '/pair', {'code': late})[0], 401, 'expired')
        for bad in [None, 12345678, 'short', 'ABCDEFG0', {'code': 'x'}]:
            self.assertIn(self.call(self.public, '/pair', {'code': bad})[0], (400, 401))
        self.assertEqual(self.call(self.public, '/pair', 'not an object')[0], 400)

    def test_pairing_attempts_are_rate_limited(self):
        public = self.serve(relay.public_handler(self.services, self.registry, pair_limit=5))
        statuses = [self.call(public, '/pair', {'code': 'AAAA-AAAA'})[0] for _ in range(7)]
        self.assertEqual(statuses[:5], [401]*5); self.assertEqual(statuses[5:], [429, 429])

    def test_registry_holds_only_hashes_and_is_private(self):
        code = self.registry.create('Remote TV', [self.ids[0]])
        raw = self.devices_path.read_text(); self.assertNotIn(code, raw)
        token = json.loads(self.call(self.public, '/pair', {'code': code})[1])['token']
        raw = self.devices_path.read_text(); self.assertNotIn(token, raw); self.assertNotIn(code, raw)
        self.assertEqual(stat.S_IMODE(os.stat(self.devices_path).st_mode), 0o600)

    # --- profile isolation ---------------------------------------------------------------
    def test_recommendations_contain_only_the_device_profile(self):
        token = self.pair(profiles=[self.ids[0]])
        status, body = self.call(self.public, '/recommendations', token=token)
        self.assertEqual(status, 200, body); data = json.loads(body)
        self.assertEqual(data['id'], self.ids[0]); self.assertEqual([p['id'] for p in data['profiles']], [self.ids[0]])
        self.assertEqual(data['items'][0]['title'], 'Synthetic pick')
        for leaked in ['household', 'Viewer Two', self.ids[1], 'household-src']:
            self.assertNotIn(leaked, body)
        lan = json.loads(self.call(self.lan, '/recommendations')[1])
        self.assertEqual([p['id'] for p in lan['profiles']], ['household']+self.ids, 'LAN bundle unchanged')
        self.assertEqual(json.loads(self.call(self.public, '/device', token=token)[1]), {'label': 'Remote TV', 'profiles': [{'id': self.ids[0], 'name': 'Viewer One'}]})

    def test_feedback_outside_scope_is_refused(self):
        token = self.pair(profiles=[self.ids[0]])
        ok = self.call(self.public, '/feedback', {'profileId': self.ids[0], 'itemId': 'flixtor:movie:1', 'preference': 'like'}, token=token)
        self.assertEqual(ok[0], 200, ok[1]); self.assertEqual(json.loads(ok[1])['state']['preference'], 'like')
        for payload in [{'profileId': self.ids[1], 'itemId': 'flixtor:movie:1', 'preference': 'like'}, {'itemId': 'flixtor:movie:1', 'preference': 'like'}, {'profileId': 'household', 'itemId': 'flixtor:movie:1', 'preference': 'like'}]:
            status, body = self.call(self.public, '/feedback', payload, token=token)
            self.assertEqual(status, 403, payload); self.assertEqual(json.loads(body)['code'], 'out-of-scope')
        self.assertEqual(self.services.profiles.store(self.ids[1]).states(), {}); self.assertEqual(self.services.profiles.store().states(), {})

    def test_profile_removed_from_registry_leaves_device_with_nothing(self):
        token = self.pair(profiles=[self.ids[1]])
        (self.directory/'profiles.json').write_text(json.dumps({'profiles': [{'id': self.ids[0], 'name': 'Viewer One'}]}))
        status, body = self.call(self.public, '/recommendations', token=token)
        self.assertEqual(status, 403); self.assertNotIn('Viewer One', body)

    # --- revocation and replacement ------------------------------------------------------
    def test_revoked_and_replaced_tokens_stop_working(self):
        token = self.pair('Remote TV')
        self.registry.revoke('remote tv')
        status, body = self.call(self.public, '/recommendations', token=token)
        self.assertEqual(status, 403); self.assertEqual(json.loads(body)['code'], 'revoked')
        fresh = self.pair('Remote TV')  # a revoked label may pair again without --replace
        self.assertEqual(self.call(self.public, '/recommendations', token=token)[0], 401, 're-paired: old token unknown')
        self.assertEqual(self.call(self.public, '/recommendations', token=fresh)[0], 200)
        with self.assertRaises(DeviceError): self.registry.create('Remote TV', [self.ids[0]])
        newer = self.pair('Remote TV', replace=True)
        self.assertEqual(self.call(self.public, '/recommendations', token=fresh)[0], 401, 'replaced token is gone')
        self.assertEqual(self.call(self.public, '/recommendations', token=newer)[0], 200)

    def test_request_rate_limit_per_device(self):
        public = self.serve(relay.public_handler(self.services, self.registry, request_limit=3))
        token = self.pair()
        self.assertEqual([self.call(public, '/device', token=token)[0] for _ in range(4)], [200, 200, 200, 429])

    def test_unreadable_registry_fails_closed(self):
        token = self.pair(); self.devices_path.write_text('{broken')
        self.assertEqual(self.call(self.public, '/recommendations', token=token)[0], 503)
        self.assertEqual(self.call(self.public, '/pair', {'code': 'AAAA-AAAA'})[0], 503)

    # --- owner tool ----------------------------------------------------------------------
    def test_pair_device_cli_resolves_names_and_lists_without_secrets(self):
        args = ['--devices', str(self.devices_path), '--data', str(self.default)]
        out = io.StringIO(); self.assertEqual(pair_device.main(args+['--label', 'Cli TV', '--profile', 'viewer one'], out), 0)
        printed = out.getvalue(); self.assertIn('Viewer One', printed); code = printed.split(': ')[1].split()[0]
        self.assertEqual(self.call(self.public, '/pair', {'code': code})[0], 200)
        out = io.StringIO(); pair_device.main(args+['--list'], out)
        self.assertIn('Cli TV', out.getvalue()); self.assertIn('paired', out.getvalue()); self.assertNotIn('sha256', out.getvalue().lower())
        with patch('sys.stderr', io.StringIO()):
            self.assertEqual(pair_device.main(args+['--label', 'Other', '--profile', 'nobody'], io.StringIO()), 1)
        self.assertEqual(pair_device.main(args+['--revoke', 'Cli TV'], io.StringIO()), 0)
        out = io.StringIO(); pair_device.main(args+['--list'], out); self.assertIn('revoked', out.getvalue())


if __name__ == '__main__':
    unittest.main()
