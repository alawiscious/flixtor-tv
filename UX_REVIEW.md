# TV experience review

A release review must test the viewer's complete task with arrow keys and OK/Back, as well as the data returned. Passing a click handler alone is insufficient.

## Space and readability

- Inspect Home, catalogue, filters, details, episode lists, feedback and player controls at 1280×720 and 1920×1080; inspect 4K scaling when available.
- Use spare horizontal space to increase useful text size. Lists of short choices should use multiple columns, with clear visual selection and focus.
- Read every sidebar action, including lower actions. Reach the last action and return with the remote; scrolling must follow focus.
- Avoid clipping long genres/titles, overlapping badges and controls, and focus rings outside the viewport.

## Catalogue truth

- A catalogue filter or sort must operate on the full source catalogue when that source supports it. Never silently filter only the current page.
- Verify genre alone, release bounds alone, rating alone, combined filters, reset, next/previous pages and return from details.
- Keep active chips, URL parameters and results consistent. Reset pagination when changing a filter. Use all source genres, not just genres present on the current page.
- An empty result needs a truthful explanation; distinguish unavailable data from no matches.

## Focus and asynchronous work

- Test arrow movement within and between columns, grid edges, final partial rows, selected choice, Back and focus restoration.
- A saved preference must not disable the focused control, jump to Back, reorder the active card or discard a second feedback choice.
- Test Good recommendation followed immediately by Already watched, slow requests, failed saves, closing during a save, and profile changes.
- Late responses must not replace unrelated dialogs or move focus out of a task.

## History and playback

- Watched episodes need a prominent text/check indicator and row treatment; colour alone is insufficient. Preserve episode numbers.
- Explicit profile completion facts must remain separate from shared source progress and must not invent playback positions or completion dates.
- Verify season boundaries and next episode against the same completion resolver used by watched indicators.
- Verify media keys and settings arrows without accidental audio changes, plus exit/return, fullscreen, sound and screensaver behaviour on physical TV.

## Background work and release evidence

- Story enrichment should run automatically with bounded requests and retries, without navigating the TV away or blocking browsing/playback.
- Distinguish worker tests from successful live-source retrieval. Report authentication/network deferrals honestly.
- Preserve live recommendations while enrichment runs. Semantic model promotion remains a separate reviewed change.
- Record actual test output, browser observations and physical-TV limitations. Prepare changes in the review checkout; publish only after the user blesses the bundle.
