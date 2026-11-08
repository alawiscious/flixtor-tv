# TV updater protocol 1

Install `alawiscious/flixtor-tv@v0.3.6` once, then fully close and reopen
TizenBrew. This migrates the native-page launcher and local service. It uses
TV loopback port 8773 so old modules on 8770 cannot intercept the new launcher.
The desktop Chrome helper uses 8771 and needs its matching service.

After migration, opening FlixTor checks the fixed GitHub stable feed. Verified
updates are downloaded to the TV, then applied on a new opening. Periodic
checks only stage files; they never reload a playing video. An **App updates**
control offers Check for updates, Apply update, and Use previous version when
one is available. No full TV reboot is part of the update protocol.

The TV service verifies RSA/SHA-256 signatures and the payload hash. Native
FlixTor pages independently verify the same signed envelope using Web Crypto,
then load the permitted inline script. FlixTor's CSP is unchanged. If Web Crypto
is unavailable, the installed native-page baseline runs instead; check this on
the physical TV before relying on future native-player updates.

The service caches current/previous/pending payloads atomically in
`/home/owner/share/.flixtor-tv-updates/state.json` on Tizen (or the user's home
directory on desktop). The native-page cache uses the FlixTor origin's local
storage. Neither contains household import data, passwords or session cookies.
The Mac need not be on for UI update checks or cached UI startup. Recommendations
still require their Mac backend.

A new payload remains a trial until its local TV interface renders and reports
health. Repeated starts without acknowledgment restore the previous payload.
Manual rollback blocks that payload's digest from being immediately reinstalled.
A failed download/signature check leaves the saved version available.

## Publish a UI release

1. Increase `package.json`'s version, main filename and files entry together.
2. Run `npm run build`, `npm run check`, and the backend checks if relevant.
3. Review and publish source/generated files and
   `updates/releases/<version>.json`. Publish `updates/stable.json` **last** if
   publishing with multiple web commits; a normal atomic Git commit may include
   both. Never overwrite a published version's payload.
4. Reopen FlixTor or use App updates → Check for updates → Apply update.

`build.cjs` signs the browser payload with the private key at the sibling path
`../private-updater/signing-key.pem`. Only `updater-public-key.json` is public.
Back up that private key privately; the build refuses to silently replace an
existing public trust key if its private key is missing or different. Do not
upload the private directory or key to GitHub.

The payload only replaces browser code. Node/service changes, new permissions,
new remote keys, a different signature key, or an incompatible bridge protocol
need a deliberate one-time module migration. Do not publish a browser payload
that assumes service endpoints the installed bridge does not support.

Validation covers cryptographic rejection, fixed download paths, staged
activation, persistent offline startup, health acknowledgment, rollback,
failed-start recovery and update-route origin/token checks. Browser QA covers
the served interface and updater dialog. Physical Samsung migration, Web Crypto,
storage access and native-page handoff still require TV validation.
