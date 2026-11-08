#!/usr/bin/env python3
"""Prepare private plot embeddings in shadow mode; never change serving settings.

Only the loopback Ollama API receives text. Missing plots remain missing, rather
than being replaced with title/genre vectors and called semantic matches.
"""
import argparse
import hashlib
import json
import math
import sqlite3
import urllib.request
from pathlib import Path

from personalize import write_json

OLLAMA = 'http://127.0.0.1:11434'


def local_call(path, payload=None):
    request = urllib.request.Request(
        OLLAMA + path, data=None if payload is None else json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def normalize(value):
    if not isinstance(value, list) or not value or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError('Model returned an invalid embedding')
    length = math.sqrt(sum(v * v for v in value))
    if not length:
        raise ValueError('Model returned a zero embedding')
    return [v / length for v in value]


def descriptions(root, db_path=None):
    root = Path(root)
    items = json.loads((root / 'catalogue.json').read_text())
    matches = json.loads((root / 'matches.json').read_text())
    all_items = {**items, **{s['item']['id']: s['item'] for s in matches['seeds']}}
    plots = {}
    plot_cache = root / 'catalogue-plots.sqlite'
    if plot_cache.exists():
        db = sqlite3.connect(plot_cache.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            for ident, title, year, text in db.execute('select id,title,year,description from plots'):
                item = all_items.get(ident)
                if item and (item['title'], item['year']) == (title, year):
                    plots[ident] = {'text': text, 'source': 'FlixTor information popup'}
        finally:
            db.close()
    for ident, item in all_items.items():
        text = ' '.join((item.get('description') or '').split())
        if len(text) >= 40 and ident not in plots:
            plots[ident] = {'text': text[:12000], 'source': 'catalogue description'}
    # Join the reviewed source identity AND source title; conflicting mappings
    # stay out. An episode synopsis is explicitly labelled as episode evidence.
    review_path = root / 'metadata_mapping_review.json'
    if db_path and review_path.exists():
        mapping = {}
        for row in json.loads(review_path.read_text()):
            mapping.setdefault((row['source_id'], row['source_title']), set()).add(row['canonical_id'])
        collected = {}
        db = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            for source_id, title, description in db.execute(
                    'select item_id,title,description from items union select item_id,title,description from watch_summaries'):
                ids = mapping.get((source_id, title), set())
                text = ' '.join((description or '').split())
                if len(ids) != 1 or len(text) < 40:
                    continue
                ident = next(iter(ids))
                if ident not in all_items or ident in plots:
                    continue
                texts = collected.setdefault(ident, [])
                if text not in texts:
                    texts.append(text)
        finally:
            db.close()
        for ident, texts in collected.items():
            is_series = all_items[ident]['type'] == 'tv'
            plots[ident] = {
                'text': '\n'.join(texts[:4])[:12000],
                'source': 'Amazon episode/series descriptions' if is_series else 'Amazon movie description'}
    documents = {}
    for ident, plot in plots.items():
        item = all_items[ident]
        documents[ident] = dict(plot, title=item['title'], playable=ident in items,
                               input='search_document: ' + item['title'] + '\n' + plot['text'])
    return documents, items, {s['item']['id'] for s in matches['seeds']}, set(matches['seen'])


def build(root, db_path=None, model='nomic-embed-text:v1.5', prepare_only=False):
    root = Path(root)
    documents, items, seeds, seen = descriptions(root, db_path)
    write_json(root / 'semantic-documents.json', documents)
    unseen = set(items) - seeds - seen
    report = {'mode': 'shadow', 'serving_changed': False, 'requested_model': model,
              'documents': len(documents), 'seed_plots': len(seeds & documents.keys()),
              'seed_total': len(seeds), 'playable_plots': len(set(items) & documents.keys()),
              'playable_total': len(items), 'unseen_playable_plots': len(unseen & documents.keys()),
              'unseen_playable_total': len(unseen), 'embedded': 0,
              'status': 'prepared', 'promotion': 'Manual review required; no automatic live switch'}
    try:
        if not prepare_only:
            models = local_call('/api/tags')['models']
            found = next((m for m in models if m['name'] == model), None)
            if not found:
                raise ValueError('Requested model is not installed locally: ' + model)
            digest = found['digest']
            path = root / 'semantic-shadow.json'
            old = json.loads(path.read_text()) if path.exists() else {}
            cached = old.get('vectors', {}) if old.get('model_digest') == digest and old.get('model') == model else {}
            vectors = {}
            for ident, document in documents.items():
                text_hash = hashlib.sha256(document['input'].encode()).hexdigest()
                entry = cached.get(ident, {})
                if entry.get('text_sha256') == text_hash:
                    embedding = normalize(entry.get('embedding'))
                else:
                    result = local_call('/api/embed', {'model': model, 'input': document['input'], 'truncate': False})
                    embedding = normalize(result['embeddings'][0])
                if vectors and len(embedding) != len(next(iter(vectors.values()))['embedding']):
                    raise ValueError('Inconsistent embedding dimensions')
                vectors[ident] = {'text_sha256': text_hash, 'embedding': embedding}
                # Checkpoint private cache; interrupted jobs resume without repeating inference.
                write_json(path, {'model': model, 'model_digest': digest, 'vectors': vectors})
            report.update(status='indexed', model_digest=digest, embedded=len(vectors))
    except (OSError, ValueError, KeyError, IndexError) as error:
        report.update(status='blocked', error=str(error))
    write_json(root / 'semantic-status.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, help='Private personalized data directory')
    parser.add_argument('--db', help='Private staged Amazon SQLite database')
    parser.add_argument('--model', default='nomic-embed-text:v1.5')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    result = build(args.data, args.db, args.model, args.prepare_only)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result['status'] == 'blocked' else 0)
