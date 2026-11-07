# FlixTor TV for TizenBrew

A remote-first interface over the live FlixTor website, with poster rails, sliding details, an on-screen keyboard and native Favorites/player integration.

## Install

In TizenBrew, select the archive-box icon at the top right, then Add GitHub Module. Enter `alawiscious/flixtor-tv@v0.3.2`. Fully restart TizenBrew and launch FlixTor TV; the interface should display 0.3.1.

This is a site-modification module, not a standalone WGT. TizenBrew launches https://flixtor.to/home and injects the bundled script. Sign-in uses FlixTor's native /vipsignin route with remote navigation and a masked on-screen password keyboard. Account sessions on the TV are separate from desktop Chrome.

## Current behavior

- Search submits to the full FlixTor /search/{encoded-title} route and displays native movie and series results.
- Favorites delegate to FlixTor's native controls; viewing progress remains with its original player. Use the website's existing Sync Code for sharing lists across devices.
- Original-site navigation has a bottom toolbar that leaves the native search controls uncovered.
- For You connects to Gorse through the local TizenBrew service. The Mac supplies recommendations from matched imported history.

## Develop

Requires Node.js; the current build/check scripts use no npm dependencies.

```sh
node build.cjs
node check.cjs
git pull --ff-only
# Edit source, rebuild, verify, then commit and push.
git push
```

Edit src/app.js, src/style.css and src/service.js. The build produces service.js, tv.js, the versioned TizenBrew bundle and FlixTor_TV_Preview.html. The standalone preview uses twelve sample titles; it does not connect to a real account. Preview fixtures test native action delegation, login keyboard, focus recovery and search integration.

Chrome tests passed for the remote keyboard, native action bridge, focus recovery after an underlying input takes focus, full-search route submission and unobstructed native search controls. Physical TV testing is still required for 0.3.0 service startup and player/codec behavior.

## Release updates

Update the manifest version/main and the build output filename together. Commit source and generated bundle, push main, then create and push a new version tag. A TV module pinned to a previous tag or commit stays on that version. Add the new tag as a GitHub module to load an update without reusing cached assets.

Official module specification: https://github.com/reisxd/TizenBrew/blob/main/docs/MODULES.md

## 0.3.0: recommendations and remote navigation

Install the pinned GitHub module `alawiscious/flixtor-tv@v0.3.2` and fully restart
TizenBrew after replacing an earlier version. This release includes a `serviceFile`;
install both the manifest and generated service, not just the injected script.

The injected script reads the signed-in FlixTor catalogue and hands title cards to
an interface served by the TizenBrew service at `http://127.0.0.1:8767/tv` on the TV.
Cards travel in the URL fragment, which is not sent in HTTP requests. FlixTor's
content security policy stays intact. Login, Favorites, Sync and playback continue
on native FlixTor pages. List changes made from recommendations open the native
title so FlixTor remains the source of truth.

The service connects to the Mac at `192.168.1.84:8766`. Its fixed endpoints provide
recommendations and accept public catalogue metadata. It cannot proxy arbitrary
URLs or access Gorse administration. If the Mac address changes, update
`relayHost` in `src/service.js`, build and publish a new pinned version.

Gorse stays on the Mac's loopback interface at port 8088. Start the LAN relay with
`backend/Start_Recommendations.command` after preparing the local import. It
accepts only localhost and the configured TV (`192.168.1.36`). Keep the Mac awake.
The staging database, mappings, user records and exports are local and excluded
from this repository. The supplied `data/catalogue-seed.json` contains public
catalogue metadata only.

The importer matches exact normalized title names, season/type hints and any year
provided; known ambiguous remakes are left unmatched. Historical watchlist adds
and at least 20 recorded minutes are weak `import_interest` signals, never likes
or completion claims. Seen movie matches are excluded from recommendations.
Episode-only names are not matched to TV series. Public cards encountered while
browsing expand the candidate pool and rerun matching locally.

Navigation now remembers the selected column when moving between rails. Search
places the remote keyboard beside results; Right at the last keyboard column
enters results, and Left from the first result column returns to the last key.
Details slide in and restore focus on Back. Reduced-motion preferences remain
supported. An unavailable recommendation server produces a retry action after a
bounded connection attempt.

Validation: `node build.cjs`, `node check.cjs`,
`python3 -m unittest discover -s backend -p 'test_*.py'`. Browser integration covers
live Gorse recommendations, native catalogue ingestion, search and remote focus.
A physical TV check is still needed for service startup and native playback.

## Browser filter update (0.3.1)

The live browser test now includes From year, To year, minimum rating and Reset
filters beside Genre and Sort. Year/rating selections use FlixTor's native
`yrf`, `yrt` and `rating` query parameters, reset pagination to the first page,
and remain active on subsequent pages. Older years can be selected by decade
with the remote. Unknown ratings do not satisfy a minimum-rating filter.

The local Chrome test opens `FlixTor_TV_Live.html` through port 8765 and uses
the recommendation bridge on port 8767. The HTML is regenerated during build,
so browser UI updates are available on the next page load.

### 0.3.2: title details and immediate cinema playback

Selecting a catalogue card opens its native title page behind the TV interface, showing FlixTor's synopsis, numerical rating and content certificate when supplied. Series include the native season/episode list. Movie details pause automatic playback until Play is selected. Favorites and progress continue to use FlixTor.

Play expands the existing player to the viewport immediately and selects the highest quality offered by its quality API after the stream is ready. It does not invent a 4K source or replace the native stream. Back from playback returns to details.

A background cover is installed as soon as the module runs, and catalogue readiness uses DOM changes instead of 400 ms polling. The Chrome helper now runs at document start in the page's JavaScript world so it can use the same player API as the TV module. TizenBrew controls when the TV module is injected; frames painted before injection cannot be concealed by this module. Physical Samsung testing remains necessary to measure any residual flash.
