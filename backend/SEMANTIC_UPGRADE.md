# Story similarity upgrade

The first stage is a private shadow index. It does not write to Gorse, change
the relay, publish data, or change the TV module. The existing metadata model
continues serving recommendations.

The 0.3.5 development build adds **For You → Gather story descriptions →
Collect next batch**. Run it in the signed-in browser with the updated Chrome
helper loaded. It reads 32 public information popups per batch, saves to the Mac,
and continues until complete or stopped. Stop or Back saves completed entries.
Unavailable entries retry after an hour. Leave the Mac relay running. The TV
uses the same collection flow after installation of the updated module; that
still requires physical TV validation.

The collector never opens watch pages or starts playback. It does not copy
session cookies. It matches each popup title against the requested catalogue
title, and the Mac also checks exact ID/title/year before accepting it. Text
remains in private `catalogue-plots.sqlite` and survives catalogue rebuilds.
Successful batches automatically update the local shadow embedding index.
Collection does not mark a title watched, liked, or added to a list.

1. Run Ollama locally with cloud features disabled:
   `OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve`
2. In a second terminal, install the official model:
   `ollama pull nomic-embed-text:v1.5`
3. Run `python3 backend/semantic_index.py --data <private-personalized-directory> --db <private-Amazon-staging.sqlite>`.
   Use `--prepare-only` to inspect description coverage without a model.

The job uses catalogue descriptions and Amazon descriptions joined through the
existing reviewed source ID plus source title mapping. Ambiguous mappings are
excluded. Series evidence can consist of up to four episode descriptions; it is
labelled accordingly, not presented as a full series synopsis. No text leaves
the Mac. Title/genre-only records do not qualify as plot documents.

Private outputs are `semantic-documents.json`, `semantic-status.json`, and
`semantic-shadow.json`. Store the data directory outside the public repository.
Embeddings are cached by model name, model digest and input text SHA-256.
Interrupted jobs checkpoint; changing model weights invalidates cached vectors.
The model request disables automatic text truncation.

## Before serving

- Obtain genuine synopsis coverage for unseen playable candidates, as well as
  history seeds. Imported history descriptions alone primarily describe titles
  already watched. Read `unseen_playable_plots` in the status report.
- Collect public descriptions through the signed-in FlixTor app using the
  collection control above, or use a separately authorized metadata source.
  Do not transfer FlixTor session cookies to the recommendation backend.
- Compare shadow semantic neighbours against current metadata recommendations.
  Review duplicate series, unwanted genre concentration, and explanations.
- Add the semantic candidate source/blend to Gorse and the relay only after
  review. Preserve existing feedback, watched exclusions and fallback behavior.
  Serving integration is not implemented by this preparatory script.

The index is not a trained preference ranker. Explicit good/bad recommendations
can later support an evaluated ranker. One combined household profile still
cannot supply meaningful collaborative neighbours.

Model/API references:
https://ollama.com/library/nomic-embed-text:v1.5
https://docs.ollama.com/capabilities/embeddings
https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
