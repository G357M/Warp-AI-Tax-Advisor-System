#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
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
OUT_DIR = ROOT / 'state' / 'scrapling-true-outlier-audit'
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
           d.document_type,
           coalesce(d.title, ''),
           length(coalesce(d.full_text, ''))::int as full_text_len,
           coalesce(cc.chunk_count, 0)::int as chunk_count
    from documents d
    left join cc on cc.document_id = d.id
    where d.language = 'ka'
      and coalesce(cc.chunk_count, 0) <= %s
      and length(coalesce(d.full_text, '')) <= %s
    order by coalesce(cc.chunk_count, 0) asc,
             length(coalesce(d.full_text, '')) desc,
             d.created_at desc
    limit %s
    '''
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (max_chunks, max_full_text_len, limit))
            rows = []
            for r in cur.fetchall():
                rows.append({
                    'document_id': r[0],
                    'source_url': r[1],
                    'document_type': r[2],
                    'title': r[3],
                    'db_full_text_len': int(r[4] or 0),
                    'db_chunk_count': int(r[5] or 0),
                })
            return rows


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

    current_md_len = len(current_md)
    base_body_len = int(diagnostics.get('base_body_len') or 0)
    scrapling_text_len = int(diagnostics.get('scrapling_text_len') or 0)

    result = {
        'uuid': uid,
        'corpus': corpus,
        'document_type': row['document_type'],
        'title': row['title'],
        'source_url': row['source_url'],
        'db_full_text_len': row['db_full_text_len'],
        'db_chunk_count': row['db_chunk_count'],
        'normalized_md_path': str(normalized_md_path) if normalized_md_path else None,
        'raw_path': str(raw_path),
        'species': detail.get('species'),
        'current_md_len': current_md_len,
        'repaired_md_len': len(repaired_md),
        'base_markdown_len': int(diagnostics.get('base_markdown_len') or 0),
        'base_body_len': base_body_len,
        'scrapling_text_len': scrapling_text_len,
        'used_scrapling': bool(diagnostics.get('used_scrapling')),
        'selected_field': diagnostics.get('selected_field'),
        'scrapling_container': diagnostics.get('scrapling_container'),
        'scrapling_legal_score': int(diagnostics.get('scrapling_legal_score') or 0),
    }
    result['delta_current_vs_base_body'] = current_md_len - base_body_len
    result['delta_scrapling_vs_base_body'] = scrapling_text_len - base_body_len
    result['delta_scrapling_vs_current'] = scrapling_text_len - current_md_len
    result['metadata_ratio'] = round(current_md_len / max(1, base_body_len), 2)
    result['scrapling_recovery_ratio'] = round(scrapling_text_len / max(1, base_body_len), 2)

    if base_body_len <= 50 and current_md_len > 1500 and scrapling_text_len > 1000:
        outlier_class = 'strong_recovery_candidate'
    elif base_body_len <= 50 and current_md_len > 1000 and scrapling_text_len > 500:
        outlier_class = 'medium_recovery_candidate'
    elif base_body_len <= 50 and scrapling_text_len == 0:
        outlier_class = 'empty_everywhere_but_wrapper'
    elif base_body_len <= 150 and current_md_len > 1200 and scrapling_text_len > base_body_len + 300:
        outlier_class = 'possible_scrapling_gain'
    else:
        outlier_class = 'metadata_wrapper_only'
    result['outlier_class'] = outlier_class

    flags = []
    if result['db_chunk_count'] <= 1:
        flags.append('chunk1')
    if base_body_len <= 50:
        flags.append('tiny_body')
    elif base_body_len <= 150:
        flags.append('small_body')
    if current_md_len > 1500:
        flags.append('long_wrapper')
    if scrapling_text_len > 1000:
        flags.append('scrapling_large')
    if scrapling_text_len > base_body_len + 300:
        flags.append('scrapling_gain')
    if scrapling_text_len == 0:
        flags.append('scrapling_empty')
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
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=250)
    ap.add_argument('--max-chunks', type=int, default=1)
    ap.add_argument('--max-full-text-len', type=int, default=3000)
    args = ap.parse_args()

    started = time.time()
    candidates = fetch_candidates(args.limit, args.max_chunks, args.max_full_text_len)
    rows = []
    for i, row in enumerate(candidates, 1):
        rows.append(audit_one(row))
        if i == 1 or i % 25 == 0:
            print(f'[audit] {i}/{len(candidates)} {rows[-1].get("document_type")} {rows[-1].get("uuid")} class={rows[-1].get("outlier_class")} flags={rows[-1].get("flags")}')

    filtered = [
        r for r in rows
        if (
            r.get('base_body_len', 0) <= 50 and r.get('current_md_len', 0) > 1000
        ) or (
            r.get('base_body_len', 0) <= 150 and r.get('scrapling_text_len', 0) > r.get('base_body_len', 0) + 300
        )
    ]

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    csv_path = OUT_DIR / f'true_outlier_audit_{ts}.csv'
    json_path = OUT_DIR / f'true_outlier_audit_{ts}.json'
    write_csv(csv_path, filtered)

    class_counts = Counter(r.get('outlier_class') or 'unknown' for r in filtered)
    type_counts = Counter(r.get('document_type') or 'unknown' for r in filtered)
    flag_counts = Counter()
    by_type_class: Dict[str, Counter] = defaultdict(Counter)
    for r in filtered:
        by_type_class[r.get('document_type') or 'unknown'][r.get('outlier_class') or 'unknown'] += 1
        for f in filter(None, str(r.get('flags') or '').split('|')):
            flag_counts[f] += 1

    summary = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'params': {
            'limit': args.limit,
            'max_chunks': args.max_chunks,
            'max_full_text_len': args.max_full_text_len,
        },
        'raw_candidates': len(rows),
        'filtered_outliers': len(filtered),
        'counts_by_type': dict(type_counts),
        'counts_by_outlier_class': dict(class_counts),
        'counts_by_type_and_class': {k: dict(v) for k, v in by_type_class.items()},
        'used_scrapling_count': sum(1 for r in filtered if r.get('used_scrapling')),
        'flag_counts': dict(flag_counts),
        'top_recovery_candidates': sorted(
            filtered,
            key=lambda r: (r.get('delta_scrapling_vs_base_body', 0), -r.get('base_body_len', 0)),
            reverse=True,
        )[:25],
        'top_wrapper_only': sorted(
            filtered,
            key=lambda r: (r.get('delta_current_vs_base_body', 0), -r.get('scrapling_text_len', 0)),
            reverse=True,
        )[:25],
        'elapsed_sec': int(time.time() - started),
    }

    json_path.write_text(json.dumps({'summary': summary, 'rows': filtered}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'summary_path': str(json_path), 'csv_path': str(csv_path), 'summary': summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
