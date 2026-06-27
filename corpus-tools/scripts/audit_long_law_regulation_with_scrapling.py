#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import psycopg2
from dotenv import dotenv_values

ROOT = Path('/root/infohub')
TOOLS_ROOT = ROOT / 'corpus-tools'
BACKEND_ROOT = ROOT / 'backend'
for path in [str(TOOLS_ROOT), str(BACKEND_ROOT)]:
    if path not in sys.path:
        sys.path.insert(0, path)

from export_pipeline.infohub_native_api import extract_structured_content  # type: ignore
from export_pipeline.scrapling_repair import (  # type: ignore
    LEGAL_HEADINGS,
    build_scrapling_repaired_payload,
)

UUID_RE = re.compile(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})')
OUT_DIR = ROOT / 'state' / 'scrapling-long-law-audit'
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


@dataclass
class DocRow:
    document_id: str
    source_url: str
    document_type: str
    title: str
    full_text_len: int
    chunk_count: int


def db_connect():
    cfg = dotenv_values(ROOT / '.env')
    password = str(cfg.get('POSTGRES_PASSWORD') or '')
    dsn = f'postgresql://infohub_user:{password}@127.0.0.1:5432/infohub_ai'
    return psycopg2.connect(dsn)


def fetch_docs(document_type: str) -> List[DocRow]:
    sql = """
    with chunk_counts as (
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
    left join chunk_counts cc on cc.document_id = d.id
    where d.document_type = %s
      and d.language = 'ka'
    order by coalesce(cc.chunk_count, 0) desc,
             length(coalesce(d.full_text, '')) desc,
             d.created_at desc
    """
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (document_type,))
            rows = []
            for r in cur.fetchall():
                rows.append(DocRow(
                    document_id=r[0],
                    source_url=r[1],
                    document_type=r[2],
                    title=r[3],
                    full_text_len=int(r[4] or 0),
                    chunk_count=int(r[5] or 0),
                ))
            return rows


def choose_sample(rows: Sequence[DocRow], *, per_type: int, min_chunks: int, min_full_text_len: int, seed: int) -> List[DocRow]:
    eligible = [r for r in rows if r.chunk_count >= min_chunks and r.full_text_len >= min_full_text_len]
    if len(eligible) <= per_type:
        return list(eligible)

    target_top = max(1, int(per_type * 0.4))
    target_len = max(1, int(per_type * 0.4))
    target_control = max(0, per_type - target_top - target_len)

    by_chunks = sorted(eligible, key=lambda r: (-r.chunk_count, -r.full_text_len, r.source_url))
    by_length = sorted(eligible, key=lambda r: (-r.full_text_len, -r.chunk_count, r.source_url))

    chosen: Dict[str, DocRow] = {}
    for row in by_chunks[:target_top]:
        chosen[row.source_url] = row
    for row in by_length[:target_len]:
        chosen[row.source_url] = row

    if len(chosen) < per_type:
        remaining = [r for r in eligible if r.source_url not in chosen]
        rnd = random.Random(seed + hash(rows[0].document_type if rows else 'x'))
        remaining.sort(key=lambda r: (-r.chunk_count, -r.full_text_len, r.source_url))
        if target_control > 0 and remaining:
            stride = max(1, len(remaining) // max(1, target_control))
            control_pick = remaining[::stride][:target_control]
            for row in control_pick:
                chosen[row.source_url] = row
        if len(chosen) < per_type:
            rnd.shuffle(remaining)
            for row in remaining:
                chosen[row.source_url] = row
                if len(chosen) >= per_type:
                    break

    return sorted(chosen.values(), key=lambda r: (r.document_type, -r.chunk_count, -r.full_text_len, r.source_url))[:per_type]


def extract_uuid(source_url: str) -> Optional[str]:
    m = UUID_RE.search(source_url or '')
    return m.group(1).lower() if m else None


def corpus_rank(name: str) -> int:
    try:
        return PREFERRED_CORPORA.index(name)
    except ValueError:
        return len(PREFERRED_CORPORA) + 100


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


def count_markers(text: str, marker: str) -> int:
    return (text or '').count(marker)


def heading_count(text: str) -> int:
    return sum((text or '').count(marker) for marker in LEGAL_HEADINGS)


def tail_token_overlap(a: str, b: str, *, chars: int = 1200) -> float:
    a_tail = (a or '')[-chars:]
    b_tail = (b or '')[-chars:]
    tok_re = re.compile(r'[\w\u10A0-\u10FF]+', re.UNICODE)
    a_tokens = set(tok_re.findall(a_tail.lower()))
    b_tokens = set(tok_re.findall(b_tail.lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))


def flags_for_row(row: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    current_len = int(row['current_md_len'])
    repaired_len = int(row['repaired_md_len'])
    scrapling_len = int(row['scrapling_text_len'])
    base_body_len = int(row['base_body_len'])
    table_count = int(row['table_count'])
    appendix_gain = int(row['repaired_appendix_count']) - int(row['current_appendix_count'])
    heading_gain = int(row['repaired_heading_count']) - int(row['current_heading_count'])
    tail_overlap = float(row['tail_overlap'])

    if repaired_len > max(current_len * 1.15, current_len + 1500):
        flags.append('repaired_much_longer')
    if scrapling_len > max(base_body_len * 1.15, base_body_len + 1200):
        flags.append('scrapling_longer_than_base_body')
    if heading_gain >= 3:
        flags.append('heading_gain')
    if appendix_gain > 0:
        flags.append('appendix_gain')
    if tail_overlap < 0.45:
        flags.append('tail_divergence')
    if table_count >= 3:
        flags.append('table_heavy')
    if row['complexity_level'] in {'complex', 'extreme'}:
        flags.append(f"complexity_{row['complexity_level']}")
    if row['used_scrapling']:
        flags.append('scrapling_selected')
    return flags


def audit_doc(doc: DocRow) -> Optional[Dict[str, Any]]:
    uuid = extract_uuid(doc.source_url)
    if not uuid:
        return None
    raw_path = locate_raw(uuid)
    if raw_path is None:
        return {
            'uuid': uuid,
            'source_url': doc.source_url,
            'document_type': doc.document_type,
            'title': doc.title,
            'db_full_text_len': doc.full_text_len,
            'db_chunk_count': doc.chunk_count,
            'error': 'raw_not_found',
        }

    corpus = raw_path.parts[4]
    normalized_md_path = locate_normalized_md(corpus, uuid)
    current_md = normalized_md_path.read_text(encoding='utf-8') if normalized_md_path and normalized_md_path.exists() else ''
    raw = json.loads(raw_path.read_text(encoding='utf-8'))
    detail = raw.get('native_detail') or {}
    repaired_payload, diagnostics = build_scrapling_repaired_payload(detail, source_url=doc.source_url)
    repaired_md = (((repaired_payload.get('data') or {}).get('markdown')) or '').strip()
    html = (((raw.get('data') or {}).get('html')) or ((raw.get('native_detail') or {}).get('description')) or '')
    structure = extract_structured_content(html)
    complexity = structure.get('complexity') or {}
    complexity_stats = complexity.get('stats') or {}

    row: Dict[str, Any] = {
        'uuid': uuid,
        'corpus': corpus,
        'document_type': doc.document_type,
        'title': doc.title,
        'source_url': doc.source_url,
        'db_full_text_len': doc.full_text_len,
        'db_chunk_count': doc.chunk_count,
        'normalized_md_path': str(normalized_md_path) if normalized_md_path else None,
        'raw_path': str(raw_path),
        'current_md_len': len(current_md),
        'repaired_md_len': int(diagnostics['repaired_markdown_len']),
        'base_markdown_len': int(diagnostics['base_markdown_len']),
        'base_body_len': int(diagnostics['base_body_len']),
        'scrapling_text_len': int(diagnostics['scrapling_text_len']),
        'scrapling_container': diagnostics.get('scrapling_container'),
        'scrapling_legal_score': int(diagnostics.get('scrapling_legal_score') or 0),
        'used_scrapling': bool(diagnostics.get('used_scrapling')),
        'selected_field': diagnostics.get('selected_field'),
        'current_heading_count': heading_count(current_md),
        'repaired_heading_count': heading_count(repaired_md),
        'current_appendix_count': count_markers(current_md, 'დანართ'),
        'repaired_appendix_count': count_markers(repaired_md, 'დანართ'),
        'tail_overlap': round(tail_token_overlap(current_md, repaired_md), 4),
        'complexity_level': complexity.get('level'),
        'complexity_signals': '|'.join(complexity.get('signals') or []),
        'table_count': int(complexity_stats.get('table_count') or 0),
        'table_rows_total': int(complexity_stats.get('table_rows_total') or 0),
        'max_table_cols': int(complexity_stats.get('max_table_cols') or 0),
        'html_len': int(complexity_stats.get('html_len') or 0),
        'html_markdown_len': int(complexity_stats.get('markdown_len') or 0),
    }
    row['delta_repaired_vs_current'] = row['repaired_md_len'] - row['current_md_len']
    row['delta_scrapling_vs_base_body'] = row['scrapling_text_len'] - row['base_body_len']
    row['flags'] = '|'.join(flags_for_row(row))
    return row


def write_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    rows = list(rows)
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
    parser = argparse.ArgumentParser(description='Audit long law/regulation docs with Scrapling vs current normalized content')
    parser.add_argument('--per-type', type=int, default=40)
    parser.add_argument('--min-chunks', type=int, default=12)
    parser.add_argument('--min-full-text-len', type=int, default=12000)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    started = time.time()
    sample: List[DocRow] = []
    for doc_type in ('law', 'regulation'):
        rows = fetch_docs(doc_type)
        picked = choose_sample(
            rows,
            per_type=args.per_type,
            min_chunks=args.min_chunks,
            min_full_text_len=args.min_full_text_len,
            seed=args.seed,
        )
        sample.extend(picked)

    audit_rows: List[Dict[str, Any]] = []
    for idx, doc in enumerate(sample, start=1):
        result = audit_doc(doc)
        if result is None:
            continue
        audit_rows.append(result)
        if idx == 1 or idx % 10 == 0:
            print(f'[audit] {idx}/{len(sample)} {doc.document_type} {result.get("uuid")} flags={result.get("flags")}')

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_base = OUT_DIR / f'long_law_regulation_audit_{ts}'
    csv_path = out_base.with_suffix('.csv')
    json_path = out_base.with_suffix('.json')

    flag_counts = Counter()
    type_counts = Counter()
    used_scrapling = 0
    complex_rows = 0
    for row in audit_rows:
        type_counts[row.get('document_type') or 'unknown'] += 1
        if row.get('used_scrapling'):
            used_scrapling += 1
        if row.get('complexity_level') in {'complex', 'extreme'}:
            complex_rows += 1
        for flag in filter(None, str(row.get('flags') or '').split('|')):
            flag_counts[flag] += 1

    top_review = sorted(
        [r for r in audit_rows if r.get('flags')],
        key=lambda r: (
            -len(str(r.get('flags') or '').split('|')),
            -int(r.get('delta_repaired_vs_current') or 0),
            -int(r.get('db_chunk_count') or 0),
        ),
    )[:30]

    summary = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'params': {
            'per_type': args.per_type,
            'min_chunks': args.min_chunks,
            'min_full_text_len': args.min_full_text_len,
            'seed': args.seed,
        },
        'sample_size': len(audit_rows),
        'counts_by_type': dict(type_counts),
        'used_scrapling_count': used_scrapling,
        'complex_rows': complex_rows,
        'flag_counts': dict(flag_counts),
        'top_review': top_review,
        'elapsed_sec': int(time.time() - started),
    }

    write_csv(csv_path, audit_rows)
    json_path.write_text(json.dumps({'summary': summary, 'rows': audit_rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'summary_path': str(json_path), 'csv_path': str(csv_path), 'summary': summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
