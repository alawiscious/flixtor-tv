# Plan: recommendations for a TV on another network

Status: **phases 1–2 done (2026-11-14); phase 3 next**. See §8. Written 2026-11-14. It supersedes the delivery parts of
`CLOUD_MIGRATION.md` if option A is chosen.

## 1. Goal

A FlixTor TV on another household network gets For You, its own recommendation profile and
feedback. It must not see other viewers' picks or names. Private viewing data stays where it is
unless the owner chooses otherwise. Alec's LAN TV keeps working unchanged throughout.

## 2. Facts this plan rests on (verified 2026-11-14)

- The relay (`backend/relay.py`) authorizes by **source IP only**: loopback + one TV address. It has
  no token or login.
- `GET /recommendations` returns **every profile** (five Netflix viewers + the Amazon household)
  in one response. The TV picks one locally.
- Gorse runs in Docker on the Mini (`127.0.0.1:8088`, SQLite data and cache in a local volume).
  The private imports are about 60 MB.
- The installed TV service forwards to `http://<LAN host>:8772`. Changing that requires a new
  **service**, which means a module reinstall. A signed UI payload cannot change it.
- The TV service already makes HTTPS requests (the updater fetches GitHub with Node `https`).
- Tailscale Funnel is permitted for the Mini's node. Tailscale serve already uses HTTPS ports
  443 (FleetView) and 8443 for **tailnet-only** apps.

### Safety constraints that follow

1. Funnel delivers public traffic to the relay **from 127.0.0.1**, which the current allowlist
   trusts. Never point Funnel at port 8772. The public path must be a separate listener that
   ignores source IP and requires a device token on every request.
2. Funnel is enabled per HTTPS port. Turning it on for 443 or 8443 would publish FleetView and the
   other tailnet-only apps. Use a **dedicated port (10000)** for FlixTor only.
3. Profile isolation has to be enforced on the server. The remote response may only contain the
   device's allowed profiles.

## 3. Options

| | A. Funnel to the Mini (recommended) | B. Small VPS | C. Vercel + Supabase (`CLOUD_MIGRATION.md`) |
|---|---|---|---|
| Where data lives | Stays on the Mini | Copied to a rented server | Copied to Supabase |
| Gorse | Unchanged | Moved (Docker) | Not supported on Vercel today; needs a worker design |
| New accounts/cost | None (Funnel is on the free plan) | VPS about $5–10/month, plus server ops | Existing accounts; usage cost unreviewed |
| Depends on | Mini + home internet up | VPS up | Several managed services |
| Work | Smallest | Medium | Largest |

Option A meets the goal with the fewest moving parts and keeps family viewing data at home. Its
weakness is availability: if the Mini or home internet is down, a remote TV shows its last saved
picks (it already caches a snapshot) until the Mini is back. If that is unacceptable, B is the next
step, and the same auth and pairing design carries over unchanged.

## 4. Design (option A)

**Relay: one handler, two access policies.**
- The existing LAN listener (`*:8772`, IP allowlist) is unchanged.
- A new public listener on `127.0.0.1:8774`, reachable only through Funnel. Every request needs
  `Authorization: Bearer <device token>`, and source IP is never consulted.
- A device registry in the private data dir (`devices.json`, mode 600) stores per device: a
  sha256 of the token, a label, the allowed profile ids, the created date and a revoked flag.
  Tokens themselves are never stored.
- Remote scope:
  - `/recommendations` is filtered to the device's profiles.
  - `/feedback` is rejected (403) for any profile outside scope.
  - `/catalogue` is accepted (public metadata, same size limits).
  - `/plots` is not offered remotely, because enrichment runs at home.
  - A per-token rate limit applies, and request logging stays off.

**Pairing (no secrets in the public repo).**
- `backend/pair_device.py --label "<TV label>" --profile <id>` prints a one-time 8-character code.
  The code is valid for 15 minutes and stored hashed.
- On the TV: Recommendations profile → **Connect to recommendations** → type the code. The TV
  service exchanges it over HTTPS (`POST /pair`) for a device token, which it stores in its private
  cache dir (mode 600). The token is never displayed.
- Revoke with `pair_device.py --revoke "<label>"`. The TV then shows "Connection removed — pair
  again".

**TV service (0.4.0, one-time module reinstall).**
- Explicit target precedence: **paired remote endpoint > LAN relay**. A `source` field reports
  which one answered.
- The HTTPS client pins its CA certificates (ISRG Root X1/X2 for Tailscale's Let's Encrypt certs)
  and keeps hostname verification on. This avoids depending on an old TV's built-in certificate
  store. It stays ES5 / Node-4 compatible.
- New endpoints `/pair` and `/connection`. The UI feature-detects them, so the update protocol
  stays at bridge 1 and older services keep working.

**UI (signed payload).** Pairing screen with the remote keyboard, connection status (home network /
remote / not paired) and clear errors: code expired, server unreachable, removed.

**Operations.**
- `tailscale funnel --bg --https=10000 http://127.0.0.1:8774`.
- The existing LaunchAgent gains `--public-port 8774 --devices <path>`.
- A health check on the public URL sends Pushover on failure and stays silent on success, like the
  other unattended jobs.

## 5. Tests

- **Backend:**
  - missing, invalid and revoked tokens get 401/403
  - each scope only sees its own profiles, and cross-profile feedback is denied
  - pairing codes are single-use and expire
  - the token is stored only as a hash
  - LAN behavior is unchanged
  - the public listener never trusts 127.0.0.1
- **Service:**
  - HTTPS against a local TLS server signed by a test CA
  - wrong-CA rejection
  - precedence and fallback
  - token file permissions
  - ES5 syntax check
- **External:** from outside the tailnet, a request without a token gets 401. With a token it sees
  only the allowed profile.
- **Physical:** pair Alec's TV in remote mode first, then Ellie's TV on her network.

## 6. Phases

1. Relay auth, device registry, pairing tool and tests (no exposure yet).
2. Funnel on :10000, LaunchAgent args and health check, then the external verification.
3. TV service HTTPS client, pairing and precedence, with tests.
4. UI pairing screen, with a browser test.
5. Release 0.4.0 (service change: reinstall the module). Validate on Alec's TV, then install on
   Ellie's TV from her Windows PC and pair it.
6. Update `README.md`, `CURRENT_STATE.md` and `UPDATING.md`. Retire the delivery parts of
   `CLOUD_MIGRATION.md`.

Phases 1–4 are reviewable PRs. Nothing is exposed publicly until phase 2, after the auth tests pass.

## 7. Decisions (2026-11-14)

1. **Hosting:** option A, Funnel to the Mini. Phase 2 (turning on Funnel and changing the
   LaunchAgent) still needs an explicit go-ahead at that point.
2. **Second TV's scope:** exactly one existing imported Netflix viewer profile. No household pack,
   no other viewers. The profile is chosen at pairing time on the Mini; names are not recorded in
   this repository.
3. **Alec's TV:** stays on the LAN relay, unchanged.

## 8. Progress

- **Phase 1** merged in #4: device registry, token-only public handler, `pair_device.py`, 12 tests.
- **Phase 2** done 2026-11-14:
  - The relay runs under its LaunchAgent with `--public-port 8774 --devices <private>/remote/devices.json`.
    Before this, the live relay was a background process from `restart_recommendations.py`, not the
    LaunchAgent. launchd now owns it; `restart_recommendations.py` refuses to start a second copy.
  - Funnel serves HTTPS port 10000 → `127.0.0.1:8774`. Ports 443 and 8443 stay tailnet-only.
  - Verified over the public ingress, not the tailnet:
    - `/health` returns 200.
    - Requests with no token or a bad token get 401. `/plots` gets 404 and browser `Origin` requests 403.
    - A temporary device scoped to one viewer saw only that profile (no household, no other viewers). Its
      feedback for other profiles got 403, and its token got 403 after revocation.
  - A health check runs every 15 minutes (owner's machine, outside this repo). It checks the public path,
    that requests without a token are refused, and the LAN relay. It sends Pushover after 2 consecutive
    failures.
- **Phase 3 note:** the Funnel certificate chain is Let's Encrypt ECDSA: `YE1` → `Root YE` → **ISRG Root X2**
  (P-384). The TV service must trust ISRG Root X2 (and X1 for the RSA chain), and the 2019 TV's Node
  runtime must support ECDSA P-384. Check that first on a real TV.
