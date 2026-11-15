# FlixTor TV: how it works today

Verified 2026-11-14 against `main` = tag `v0.4.0` (`2a82484`). It is read from source, the
public update feed and the release tooling. Items marked **OPEN** are not established.
Older sections of `README.md` describe earlier releases. Where they disagree, this file wins.

## 1. What runs where

| Layer | Source | Runs on | Updated by |
| --- | --- | --- | --- |
| Stable launcher | `src/launcher.js` → `tv-<version>.js` | FlixTor pages inside TizenBrew | Module (re)install only |
| TV service | `src/updater-service.js` + `src/service.js` → `service.js` | TizenBrew service on the TV, `127.0.0.1:8773` | Module (re)install only |
| Overlay UI | `src/app.js`, helper modules, `src/style.css` → `tv.js` / signed payload | TV shell (`127.0.0.1:8773/tv`) and FlixTor `/watch/` pages | Signed updater (no reinstall) |
| Native FlixTor | flixtor.to | TV browser | n/a. Login, Favorites, Sync Code, playback and resume positions stay native |
| Recommendations relay | `backend/relay.py` (+ Gorse in Docker, loopback only) | Home Mac, see §4 | Manual restart on the Mac |

The bundle composition (module order) is defined once in `bundle.cjs` (used by `build.cjs` and the
tests) since 0.3.14.

## 2. Navigation and page modes

1. TizenBrew opens `https://flixtor.to/home`. The launcher redirects to the TV shell
   `http://127.0.0.1:8773/launch`. The shell checks for updates, then serves the newest verified
   payload at `/tv` with the catalogue snapshot in the URL fragment.
2. Selecting a title assigns `https://flixtor.to/watch/<type>/<id>#ftv-details=<context>`. The
   launcher verifies the cached signed payload with Web Crypto and injects it. `app.js` runs in
   **details mode** and renders details over the native page.
3. **Movie Play** stays on the same document: `startPlayback()` hides the overlay and switches the
   native JW player to cinema mode. **Episode Play** calls `startPlayback()` and then clicks the
   native episode row.
4. **Back during playback (details mode)** runs the playback exit and restores details on the same
   document. Back from details calls `history.back()`.
5. Other hashes: `#ftv-play` / `#ftv-return` (Back uses history), `#ftv-similar`,
   `#ftv-original` / `#ftv-search` (native site with the bottom remote bar).

## 3. Playback lifecycle modules

| Module | Role | Teardown |
| --- | --- | --- |
| `player.js` | Highest offered quality, sound and volume helpers | stateless |
| `player-ui.js` | Remote Settings menu (Audio, Subtitles, Quality, Next) | `destroy()` |
| `playback-power.js` | Samsung screensaver suppression or browser wake lock | `destroy()` restores protection |
| `next-episode.js` | Next-episode panel; delegates to the native row click | `destroy()` |
| `watch-history.js` | Reads native `pos:` localStorage keys; never writes them | stateless |
| `playback-exit.js` | Idempotent isolated teardown, pause via player API, bounded details-page pause guard | since 0.3.14 |

## 4. Recommendations: verified deployment

- TV services up to 0.3.14 forward `/recommendations`, `/catalogue`,
  `/feedback` and `/plots` over **plain HTTP to `relayHost:8772`**. Since 0.4.0 an unpaired TV
  still does exactly this; a paired TV sends them to the remote endpoint instead (see below). `relayHost` defaults to the home
  Mac's LAN address in `src/service.js`. The port is fixed, and a TV cannot set the environment
  override.
- The relay accepts requests only from loopback and one configured TV address. Gorse listens on
  the Mac's loopback interface only.
- No HTTPS or externally hosted endpoint appears in any released service, in the repository, or in
  the Mac's service configuration. `CLOUD_MIGRATION.md` is a proposal; it states that nothing was
  created.
- Consequence: a TV on another network gets normal FlixTor browsing, playback and signed UI
  updates. For You and profile feedback will fail there with "Start the recommendation relay".
- Changing the recommendation endpoint changes the TV **service**, so it needs a module
  reinstall. A signed UI payload cannot change it (see `UPDATING.md`).
- **Remote recommendations (0.4.0):** the relay also runs a token-only listener on `127.0.0.1:8774`,
  published through Tailscale Funnel on HTTPS port 10000. Each paired device sees only its own profiles
  (`backend/devices.py`; pair with `backend/pair_device.py --label … --profile …`). The 0.4.0 TV service
  (`src/remote-service.js`) pairs over HTTPS pinned to ISRG Root X1/X2 (`remote-trust.json`), stores
  the token in `remote.json` (mode 600), and uses one precedence: paired remote, else LAN. The UI pairing
  screen is under Recommendations profile → Connect to recommendations. Pairing needs the 0.4.0
  **service** (module re-added once); a 0.3.x service shows no pairing controls.
- **OPEN (historical):** the owner reports that recommendations were moved outside the home network. A full
  search on 2026-11-14 found no such deployment: no cloud project (Vercel lists none for FlixTor),
  no tunnel or remote Docker host, no backend repo, and no running relay outside the home Mac. The
  relay has no token authentication; it allows requests by source IP only. If that work exists, it
  was done in the former cloud workspace and is not in this repository. Its endpoint, auth model
  and profile isolation must be identified before any TV is pointed at it.

## 5. Signed update and release path

- TVs poll `https://raw.githubusercontent.com/alawiscious/flixtor-tv/main/updates/stable.json`
  (verified live: `0.4.0`, sha256 `7f3d03dd…d4218c6a`). A git tag or GitHub Release alone does
  **not** update an installed TV; only `main`'s stable feed does.
- `build.cjs` builds the bundle and signs the payload (RSA-SHA256) with the private key at
  `../private-updater/signing-key.pem` (sibling of the checkout, never in git). It refuses to run
  if that key is missing or does not match the pinned `updater-public-key.json`. It writes
  `updates/releases/<v>.json`, `updates/stable.json`, `tv-<v>.js`, `service.js`, `tv.js`, previews
  and the Chrome helper.
- **Caveat:** `build.cjs` writes `tv.js` before it checks for the key. A failed build leaves
  tracked output modified. Build releases in a scratch worktree.
- Publish order: the payload (`updates/releases/<v>.json`) first and `updates/stable.json` last,
  or both in one atomic commit. Never rewrite a published payload.
- TV behavior: a staged payload becomes active on the next FlixTor opening. It stays a trial
  until the shell reports healthy. Repeated unacknowledged starts roll back. **App updates →
  Use previous version** is the manual rollback.
- The module install tag (`alawiscious/flixtor-tv@vX.Y.Z`) only matters for first install or a
  service migration. The current service protocol dates from 0.3.6.

## 6. Tests

| Command | Covers | Does not cover |
| --- | --- | --- |
| `npm run check` | vm and fixture unit tests, updater crypto and HTTP flows | Real browser layout, Samsung |
| `npm run check:browser` | Headless Chrome: playback → Back → details lifecycle, Home hero layout, pairing screen (needs Chrome/Chromium) | FlixTor's real player, Samsung media stack |
| `python3 -m unittest discover -s backend -p 'test_*.py'` | Relay, profiles, feedback, imports, paired-device listener (78 tests) | Live Gorse |

macOS runs the HTTP updater test natively. The `spawn E2BIG` failure was Linux-only.

## 7. Known issues (2026-11-14)

- **Playback → Back → frozen details → crash on Samsung.** Fix released in 0.3.14. It passes in
  Chrome; its probable cause is not confirmed and it is not yet verified on a Samsung TV.
- Home hero long-title overflow: fixed in 0.4.0 (Chrome-verified at 720p/1080p/4K; not yet seen on a TV).
- Remote pairing: released in 0.4.0. Not yet verified on a Samsung TV, in particular the 2019 model's
  Node/OpenSSL handshake with the Let's Encrypt ECDSA chain.
