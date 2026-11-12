# Remove the home Mac dependency

Proposed architecture using existing Vercel and Supabase accounts. No cloud resources or databases have been created, and no viewing data has been uploaded by this review.

## Responsibilities

| Component | Owner |
| --- | --- |
| Source, public assets and signed TV releases | GitHub |
| Authenticated recommendation/profile/feedback API | Vercel Functions |
| Private household/viewer records, feedback, episode assertions and saved picks | Supabase Postgres, with tested access policies |
| Public title catalogue and synopsis/embedding metadata | Supabase tables/storage, delivered through the API |
| Training, enrichment and recommendation generation | Candidate: Vercel Daemon running a private worker |
| Native playback, Favorites, Sync Code and actual resume positions | FlixTor |
| Read-only last good picks when disconnected | TV snapshot cache |

Access to the existing personal Pro accounts was verified through their dashboards. Included capacity, worker eligibility and incremental usage charges still need review before enabling resources. Do not create a second subscription or reuse business/customer data stores for family viewing records.

## Gorse feasibility gate

Vercel Daemons is currently a public-beta service for continuous outbound/polling workers. It does not presently provide inbound HTTP/TCP service or persistent local filesystem storage. It is a candidate, not yet a validated Gorse hosting configuration.

A proof should run the reviewed Gorse container privately alongside a worker controller. The controller polls pending work from Supabase, loads allowed derived taste signals and the public catalogue, calls Gorse over container loopback, and writes generated picks back to Supabase. Vercel's HTTP API reads those saved picks; it does not expose Gorse administration or require inbound access to the daemon.

Persistent state must live outside the container. Validate model/checkpoint storage compatibility or prove safe dataset reconstruction after a restart. Confirm memory/CPU capacity, single active trainer ownership, graceful deployment replacement, feedback replay/idempotency, per-profile isolation and cost before adopting this design. If unsuitable, choose another already-owned container platform; do not silently substitute a simpler recommendation engine.

Feedback should hide watched/disliked titles immediately on the API, while background work refreshes ranking. An unavailable trainer must retain usable saved picks with a generation date and stale status.

## Data and device access

Keep household/viewer identities, imported taste signals, feedback and episode facts private. Raw Amazon/Netflix exports remain local unless their upload is separately part of an approved migration. Public GitHub must contain no histories, recommendation snapshots, credentials or model-training data tied to family members.

Pair each TV/device to the household through a revocable device credential. Apply household/viewer authorization on every API operation and test cross-household denial, not merely allowed reads. Supabase privileged service credentials stay server-side. Native FlixTor credentials and Sync Codes are not needed by this backend and must not be copied to it.

## TV migration

The installed bridge currently forwards fixed routes to a home-LAN HTTP address. Cloud operation therefore needs one module/service update to support the authenticated HTTPS API; the ordinary signed UI payload cannot rewrite that installed service. Preserve current updater verification and rollback. Test TLS/certificates, login pairing, profile selection, feedback and offline picks on the actual Samsung, including an older model before remote family rollout.

## Cutover sequence

1. Validate container recovery and estimate resource use against existing plans.
2. Prepare a dedicated private schema/project, migrations, access policies and read/write isolation tests.
3. Import only the approved derived household/viewer state; reconcile counts and retain the local original.
4. Run training and compare saved picks without changing the live TV backend.
5. Package and test one-time bridge migration, including pairing and rollback.
6. Switch the TV after the user reviews the concrete deployment and any incremental resource cost. Retain the Mac route until cloud operation and recovery are verified.

References checked 2026-11-11: https://vercel.com/daemons ; https://vercel.com/docs/functions ; https://supabase.com/docs/guides/database/postgres/row-level-security ; https://gorse.io/docs/concepts/pipeline
