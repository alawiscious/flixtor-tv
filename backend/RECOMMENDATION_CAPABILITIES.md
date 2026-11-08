# Recommendation capabilities

| Capability | Status | Implementation/data requirement |
|---|---|---|
| Genre similarity | Active | Normalized genre tags from catalogue and local metadata |
| Content metadata embedding | Active | Normalized genre, release-era and media-type vectors in Gorse; not neural plot understanding |
| Shared creators | Active | Official IMDb director/writer IDs, applied by the relay when comparing candidates |
| Explicit feedback | Active | Independent recommendation preference and watched state, persisted in private SQLite |
| Stronger explicit interests | Active | Explicit Amazon likes and user recommendation votes outweigh ordinary inferred viewing |
| Negative recommendation feedback | Active | Excludes that title and gently lowers similar picks |
| Recency and diversity | Active | Recent-interest weighting plus a diversity penalty during selection |
| Watched exclusion and undo | Active | Independent seen state; explicit Not watched can override imported exclusion |
| Collaborative matrix factorization | Not enabled | Needs multiple independent real profiles with overlapping feedback |
| User-to-user similarity | Not enabled | One household profile cannot establish useful neighbours |
| Gorse FM learned ranker | Not enabled | Needs meaningful positive and negative labels and evaluation before promotion |
| Neural plot/semantic matching or LLM reranking | Not enabled | Needs plot data, a local model or an approved API; no viewing history is sent to an external model |

Gorse enables genre, metadata embedding and creator indexes. Its untrained ranker configuration permits one serving candidate source, so metadata is the primary source and the local relay blends the additional evidence. We do not enable an untrained FM model merely to select multiple recommenders.

Recommendation feedback types are `recommend_like`, `recommend_dislike`, `recommend_watched` and `recommend_unwatched`. The last is an override, not negative taste. Feedback is scoped to the current household profile, uses only catalogue IDs, cannot choose another profile through a request, and is retained in an outbox if Gorse is temporarily offline. It stays separate from imported evidence and native FlixTor state.

Rebuild features with `python3 backend/recommendation_features.py --data <private-personalized-directory> --crew <official-title.crew.tsv.gz>`. The private metadata index should include catalogue keys via `history_index.py --catalogue <private-catalogue.json>`, as well as history and explicit-feedback keys. The feature-input path is retained privately so future catalogue imports rebuild features without erasing user feedback.

Information courtesy of IMDb (https://www.imdb.com). Used with permission. Bulk data and derived household metadata remain private and are used for individual personal, non-commercial purposes.
