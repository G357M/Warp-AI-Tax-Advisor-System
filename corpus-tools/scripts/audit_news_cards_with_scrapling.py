#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from dotenv import dotenv_values

ROOT = Path('/root/infohub')
for path in [str(ROOT / 'corpus-tools'), str(ROOT / 'backend')]:
    if path not in sys.path:
        sys.path.insert(0, path)

from export_pipeline.scrapling_repair import build_scrapling_repaired_payload  # type: ignore

UUID_RE = re.compile(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})')
OUT_DIR = ROOT / 'state' / 'scrapling-news-card-audit'
PREFERRED_CORPORA = [
    'live-native-legislative-news',
    'live-native-newdocument',
    'native-api-c2-legislative-news-p1-20',
    'native-api-c21-legislative-news-p1-20',
    'native-api-c22-legislative-news-p1-20',
    'native-api-c2-newdocument-p1-20',
    'native-api-c21-newdocument-p1-20',
    'native-api-pilot',
]


def db_connect():
    cfg = dotenv_values(ROOT / '.env')
    password = str(cfg.get('POSTGRES_PASSWORD') or '')
    dsn = f'postgresql://infohub_user:{password}@127.0.0.1:5432/infohub_ai'
    return psycopg2.connect(dsn)


def corpus_rank(name: str) -> int:
    try:
        return PREFERRED_CORPORA.index(name)
    except ValueError:
        return len(PREFERRED_CORPORA) + 100


def fetch_candidates(limit: int, max_chunks: int, max_full_text_len: int) -> List[Dict[str, Any]]:
    sql = '''
    with cc as (
      select document_id, count(*)::int as chunk_count
      from document_chunks
      group by document_id
    )
    select d.id::text,
           d.source_url,
           coalesce(d.title, ''),
           length(coalesce(d.full_text, ''))::int as full_text_len,
           coalesce(cc.chunk_count, 0)::int as chunk_count
    from documents d
    left join cc on cc.document_id = d.id
    where d.document_type = 'news'
      and d.language = 'ka'
      and (
        coalesce(cc.chunk_count, 0) <= %s
        or length(coalesce(d.full_text, '')) <= %s
      )
    order by coalesce(cc.chunk_count, 0) asc,
             length(coalesce(d.full_text, '')) asc,
             d.created_at desc
    limit %s
    '''
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (max_chunks, max_full_text_len, limit))
            out = []
            for r in cur.fetchall():
                out.append({
                    'document_id': r[0],
                    'source_url': r[1],
                    'title': r[2],
                    'db_full_text_len': int(r[3] or 0),
                    'db_chunk_count': int(r[4] or 0),
                })
            return out


def extract_uuid(source_url: str) -> Optional[str]:
    m = UUID_RE.search(source_url or '')
    return m.group(1).lower() if m else None


def locate_raw(uuid: str) -> Optional[Path]:
    matches = list((ROOT / 'corpus').glob(f'*/raw/documents/{uuid}/raw.json'))
    if not matches:
        return None
    matches.sort(key=lambda p: (corpus_rank(p.parts[4]), str(p)))
    return matches[0]


def locate_normalized_md(corpus: str, uuid: str) -> Optional[Path]:
    matches = list((ROOT / 'corpus' / corpus / 'normalized').glob(f'**/{uuid}/document.md'))
    if not matches:
        return None
    matches.sort()
    return matches[0]


def audit_one(row: Dict[str, Any]) -> Dict[str, Any]:
    uid = extract_uuid(row['source_url'])
    if not uid:
        return {**row, 'error': 'uuid_not_found'}
    raw_path = locate_raw(uid)
    if raw_path is None:
        return {**row, 'uuid': uid, 'error': 'raw_not_found'}

    corpus = raw_path.parts[4]
    normalized_md_path = locate_normalized_md(corpus, uid)
    current_md = normalized_md_path.read_text(encoding='utf-8') if normalized_md_path and normalized_md_path.exists() else ''
    raw = json.loads(raw_path.read_text(encoding='utf-8'))
    detail = raw.get('native_detail') or {}
    repaired_payload, diagnostics = build_scrapling_repaired_payload(detail, source_url=row['source_url'])
    repaired_md = (((repaired_payload.get('data') or {}).get('markdown')) or '').strip()

    result = {
        'uuid': uid,
        'corpus': corpus,
        'title': row['title'],
        'source_url': row['source_url'],
        'db_full_text_len': row['db_full_text_len'],
        'db_chunk_count': row['db_chunk_count'],
        'normalized_md_path': str(normalized_md_path) if normalized_md_path else None,
        'raw_path': str(raw_path),
        'species': detail.get('species'),
        'current_md_len': len(current_md),
        'repaired_md_len': len(repaired_md),
        'base_markdown_len': int(diagnostics.get('base_markdown_len') or 0),
        'base_body_len': int(diagnostics.get('base_body_len') or 0),
        'scrapling_text_len': int(diagnostics.get('scrapling_text_len') or 0),
        'used_scrapling': bool(diagnostics.get('used_scrapling')),
        'selected_field': diagnostics.get('selected_field'),
        'scrapling_container': diagnostics.get('scrapling_container'),
        'scrapling_legal_score': int(diagnostics.get('scrapling_legal_score') or 0),
    }
    result['delta_current_vs_base_body'] = result['current_md_len'] - result['base_body_len']
    result['delta_scrapling_vs_base_body'] = result['scrapling_text_len'] - result['base_body_len']
    result['delta_current_vs_repaired'] = result['current_md_len'] - result['repaired_md_len']
    flags = []
    if result['db_chunk_count'] <= 1:
        flags.append('chunk1')
    elif result['db_chunk_count'] == 2:
        flags.append('chunk2')
    if result['db_full_text_len'] < 500:
        flags.append('very_short_db_text')
    if result['scrapling_text_len'] > result['base_body_len'] + 500:
        flags.append('scrapling_longer')
    if result['scrapling_text_len'] < result['base_body_len'] - 1000:
        flags.append('scrapling_shorter')
    if result['used_scrapling']:
        flags.append('scrapling_selected')
    result['flags'] = '|'.join(flags)
    return result


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open('w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=60)
    ap.add_argument('--max-chunks', type=int, default=2)
    ap.add_argument('--max-full-text-len', type=int, default=5000)
    args = ap.parse_args()

    started = time.time()
    candidates = fetch_candidates(args.limit, args.max_chunks, args.max_full_text_len)
    rows = []
    for i, row in enumerate(candidates, 1):
        rows.append(audit_one(row))
        if i == 1 or i % 10 == 0:
            print(f'[audit] {i}/{len(candidates)} {rows[-1].get("uuid")} flags={rows[-1].get("flags")}')

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    csv_path = OUT_DIR / f'news_card_audit_{ts}.csv'
    json_path = OUT_DIR / f'news_card_audit_{ts}.json'
    write_csv(csv_path, rows)

    used_scrapling = sum(1 for r in rows if r.get('used_scrapling'))
    flag_counts = Counter()
    for r in rows:
        for f in filter(None, str(r.get('flags') or '').split('|')):
            flag_counts[f] += 1

    summary = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'params': {
            'limit': args.limit,
            'max_chunks': args.max_chunks,
            'max_full_text_len': args.max_full_text_len,
        },
        'sample_size': len(rows),
        'used_scrapling_count': used_scrapling,
        'flag_counts': dict(flag_counts),
        'avg_db_full_text_len': round(sum(r.get('db_full_text_len', 0) for r in rows) / max(1, len(rows)), 1),
        'avg_current_md_len': round(sum(r.get('current_md_len', 0) for r in rows) / max(1, len(rows)), 1),
        'avg_base_body_len': round(sum(r.get('base_body_len', 0) for r in rows) / max(1, len(rows)), 1),
        'avg_scrapling_text_len': round(sum(r.get('scrapling_text_len', 0) for r in rows) / max(1, len(rows)), 1),
        'avg_delta_scrapling_vs_base_body': round(sum(r.get('delta_scrapling_vs_base_body', 0) for r in rows) / max(1, len(rows)), 1),
        'avg_delta_current_vs_repaired': round(sum(r.get('delta_current_vs_repaired', 0) for r in rows) / max(1, len(rows)), 1),
        'top_scrapling_longer': sorted(
            [r for r in rows if r.get('scrapling_text_len', 0) > r.get('base_body_len', 0)],
            key=lambda r: (r.get('scrapling_text_len', 0) - r.get('base_body_len', 0)),
            reverse=True,
        )[:15],
        'top_scrapling_shorter': sorted(
            rows,
            key=lambda r: (r.get('scrapling_text_len', 0) - r.get('base_body_len', 0)),
        )[:15],
        'elapsed_sec': int(time.time() - started),
    }

    json_path.write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'summary_path': str(json_path), 'csv_path': str(csv_path), 'summary': summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
