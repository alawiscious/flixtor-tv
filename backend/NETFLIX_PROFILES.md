# Private Netflix recommendation profiles

`netflix_import.py` imports only named profiles, viewing activity, ratings and My List interest from a Netflix account-data ZIP. It does not extract arbitrary archive paths or copy billing, addresses, email, device or location fields into the staging database. Keep the original archive, staging DB, profile manifest, matching review and recommendation snapshots outside this repository.

The importer deduplicates repeat events and uses deterministic Gorse user IDs. Supplemental videos and viewing shorter than two minutes are excluded from taste matching; at least twenty accumulated recorded minutes makes a viewing-interest seed. Viewing does not imply liking or completion. Native FlixTor lists/progress are not modified.

The included Netflix data dictionary defines thumbs 0/1/2/3 as not rated/down/up/double up. Stars 1–2 are negative, 3 neutral and 4–5 positive; special star 0 clears a rating, -1 is not interested and -2 is not seen. Latest explicit state is applied per title. Unknown encodings remain uninterpreted. Uncertain title collisions stay in private matching-review output; the local IMDb index is partial, so coverage is partial too. A historical My List entry is weak interest, not a request to add a title to FlixTor Favorites.

Arguments: `--archive`, `--db`, `--catalogue`, `--metadata`, `--out`; `--apply` writes verified, profile-scoped signals to local Gorse. Re-running the same archive is idempotent. Rerun after extending the catalogue or metadata index. The original unassigned Amazon profile is retained separately; no automatic family-member attribution is performed.

`profiles.py` reads the private registry from `private-imports/netflix/profiles` alongside the existing private Amazon directory. The existing `/recommendations` response retains its legacy household fields and adds named recommendation packs. `/feedback` accepts an allowlisted `profileId` and persists feedback in that profile's own store. Arbitrary paths and unknown profile IDs are rejected. No profile contents are included in app bundles or public GitHub updates.

The TV's Recommendations profile action switches recommendation packs; the For You heading identifies the active profile. The choice is remembered for the browser session. FlixTor's current Sync Code still controls My List and playback progress. This chooser does not create separate native FlixTor accounts, Sync Codes, parental controls or playback-progress stores.

After updating backend source on the Mac, run `python3 backend/restart_recommendations.py` in the repository from Terminal. It restarts only the listener matching this project's recorded relay PID, launches it detached and verifies the profile response. Close and reopen FlixTor to activate a compatible signed UI update. The Mac must remain available for these private recommendations; this does not deploy cloud hosting.

Validation: backend unit tests include rating decoding, trailer filtering, safe archive reads, replay deduplication, unknown profiles, title ambiguity, explicit not-seen behavior, profile feedback isolation, allowlist enforcement and legacy response compatibility.
