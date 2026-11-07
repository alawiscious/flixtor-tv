# FlixTor TV for TizenBrew

A remote-first interface over the live FlixTor website, with poster rails, sliding details, an on-screen keyboard and native Favorites/player integration.

## Install

In TizenBrew, select the archive-box icon at the top right, then Add GitHub Module. Enter `alawiscious/flixtor-tv@v0.2.4`. Fully restart TizenBrew and launch FlixTor TV; the interface should display 0.2.4.

This is a site-modification module, not a standalone WGT. TizenBrew launches https://flixtor.to/home and injects the bundled script. Sign-in uses FlixTor's native /vipsignin route with remote navigation and a masked on-screen password keyboard. Account sessions on the TV are separate from desktop Chrome.

## Current behavior

- Search submits to the full FlixTor /search/{encoded-title} route and displays native movie and series results.
- Favorites delegate to FlixTor's native controls; viewing progress remains with its original player. Use the website's existing Sync Code for sharing lists across devices.
- Original-site navigation has a bottom toolbar that leaves the native search controls uncovered.
- Gorse is not connected to this module yet. The live For You view uses FlixTor recommendations.

## Develop

Requires Node.js; the current build/check scripts use no npm dependencies.

```sh
node build.cjs
node check.cjs
git pull --ff-only
# Edit source, rebuild, verify, then commit and push.
git push
```

Edit src/app.js and src/style.css. The build produces tv.js, the versioned TizenBrew bundle and FlixTor_TV_Preview.html. The standalone preview uses twelve sample titles; it does not connect to a real account. Preview fixtures test native action delegation, login keyboard, focus recovery and search integration.

Chrome tests passed for the remote keyboard, native action bridge, focus recovery after an underlying input takes focus, full-search route submission and unobstructed native search controls. Physical TV testing is still required for the 0.2.4 search changes and for player/codec behavior.

## Release updates

Update the manifest version/main and the build output filename together. Commit source and generated bundle, push main, then create and push a new version tag. A TV module pinned to a previous tag or commit stays on that version. Add the new tag as a GitHub module to load an update without reusing cached assets.

Official module specification: https://github.com/reisxd/TizenBrew/blob/main/docs/MODULES.md
