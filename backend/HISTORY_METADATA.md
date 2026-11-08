# Local Amazon history enrichment

The recommender learns from identified films and series even when they are not in the playable FlixTor catalogue. History-only items remain hidden in Gorse and never receive the `playable` category. The TV recommendation endpoint continues to return only known FlixTor items. No viewing-title searches or raw history uploads are made to metadata providers.

## Inputs and privacy

Keep Amazon exports, the staging SQLite database, IMDb downloads, the targeted metadata index, mapping reviews and backups outside this repository, under the private import directory. The public code contains no household history or exported metadata.

The metadata input consists of official `title.basics.tsv.gz`, `title.episode.tsv.gz` and `title.ratings.tsv.gz` files from https://datasets.imdbws.com/. They provide title identities, episode-to-series relationships, genres and vote counts. Use only for individual personal, non-commercial purposes under https://developer.imdb.com/non-commercial-datasets/.

Information courtesy of IMDb (https://www.imdb.com). Used with permission.

`metadata/explicit-feedback.json` contains only Customer Feedback rows from the Amazon export: Entity Type, Feedback Date, Feedback Type and Title Name. Other account, location, PIN and device fields are not used.

## Rebuild

Build the index with `python3 backend/history_index.py --basics <download> --episodes <download> --ratings <download> --db <private-staging-db> --feedback <private-feedback-json> --out <private-import-directory>/metadata/title-index.sqlite`. Include the feedback file so likes absent from viewing-history tables are indexed too.

Run the normal `backend/personalize.py --db ... --catalogue ... --out <private-import-directory>/personalized --apply`. It automatically discovers the sibling metadata index and explicit feedback file. Catalogue refreshes therefore preserve enrichment.

## Matching and safeguards

- Exact normalized titles, media type, year, observed playback bounds and watch date constrain identities. Ambiguous remakes are left unresolved.
- Episode-only titles need an independently supported series identity. Compound Amazon episode/series/season titles preserve the explicit series information.
- A unique full movie with at least 1,000 IMDb votes may be accepted when the only collisions are unsupported review episodes. Multiple movie identities are never ranked by popularity to guess a match.
- Episodes roll up to one series. Playback and watch summaries use the maximum recorded time for the same episode/title rather than adding overlapping observations.
- Watching is a seen/interest signal, not proof of liking or completion. Explicit likes retain their own feedback type. The most recent explicit like/dislike controls that title. Historical watchlist additions remain weak interest and do not change FlixTor Favorites.
- Gorse context size includes the full set of resolved interest titles instead of only the latest 100. The persisted local TOML also reserves 512 entries.

Private coverage, unresolved and mapping reports show remaining gaps. The prior private reports and Gorse config/feedback are retained in `before-metadata-remedy` for review/recovery.
