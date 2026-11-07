# Full browser test

This local Chrome extension runs the same generated TV module on FlixTor pages.
It reapplies the interface after native search, catalogue, list and title
navigations. It is limited to `https://flixtor.to/*`; it requests no background,
tabs, browser-history, cookies API, or access to other websites.

Keep the browser service running on this Mac:

```sh
FTV_RELAY_HOST=127.0.0.1 node service.js
```

The recommendation relay and Gorse must also be running for For You. Existing
FlixTor login, Favorites, Sync and playback stay with FlixTor. The extension does
not copy account cookies to the recommendation service.

After approving installation, open Chrome's extension manager, enable Developer
mode, choose Load unpacked and select this `chrome` folder. Then open
`https://flixtor.to/home` in Chrome. The module hands the live catalogue to the
local TV interface automatically. Do not use the sample HTML preview for this
test.

Run `node build.cjs` after code changes, then reload the extension in Chrome.
Remove the extension in Chrome's extension manager when finished testing.

The Chrome helper hands off to `FlixTor_TV_Live.html` on the loopback preview server at port 8765. Start that server with `python3 -m http.server 8765 --bind 127.0.0.1` in the repository root. Rebuilding updates the browser UI on the next page load. The API bridge and TV module use port 8767.
