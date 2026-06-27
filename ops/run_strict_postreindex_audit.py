import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/infohub')
CORPUS_ROOT = ROOT / 'corpus'
AUDIT_DIR = ROOT / 'audits'
STATE_DIR = ROOT / 'state'
DB_STATS = STATE_DIR / 'db_doc_stats_postreindex.jsonl'
OLD_AUDIT = AUDIT_DIR / 'invariant_audit_v3_20260410_214438.csv'
TIMESTAMP = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
OUT_PREFIX = AUDIT_DIR / f'invariant_audit_v3_postreindex_{TIMESTAMP}'
IMPORTANT_TYPES = {'court_decision', 'regulation', 'law', 'news'}


def choose_raw_body(native_detail, data):
    candidates = []
    for field in ['description', 'additionalDescription', 'documentDecisionContent']:
        val = (native_detail or {}).get(field)
        if isinstance(val, str) and val.strip():
            candidates.append((f'native_detail.{field}', val))
    for field in ['description', 'body', 'content']:
        val = (data or {}).get(field)
        if isinstance(val, str) and val.strip():
            candidates.append((f'data.{field}', val))
    if not candidates:
        return '', ''
    return max(candidates, key=lambda item: len(item[1]))


def classify(rec):
    flags = []
    raw_len = int(rec.get('raw_body_proxy_len') or 0)
    db_len = int(rec.get('db_full_text_len') or 0)
    chunk_count = int(rec.get('chunk_count') or 0)
    doc_type = (rec.get('document_type') or '').strip()
    title = (rec.get('title') or '').strip()
    raw_field = (rec.get('raw_body_field') or '').strip()
    ratio = (db_len / raw_len) if raw_len > 0 else 1.0

    if ratio < 0.10:
        flags.append('V3_RAW_TO_NORM_LT_10PCT')
    if ratio < 0.05:
        flags.append('V3_RAW_TO_NORM_LT_5PCT')
    if raw_len >= 5000 and db_len <= 500:
        flags.append('V3_RAW5K_NORM_LE_500')
    if raw_len >= 10000 and db_len <= 1000:
        flags.append('V3_RAW10K_NORM_LE_1K')
    if raw_len >= 20000 and db_len <= 2000:
        flags.append('V3_RAW20K_NORM_LE_2K')
    if raw_len >= 50000 and db_len <= 5000:
        flags.append('V3_RAW50K_NORM_LE_5K')
    if raw_len >= 5000 and chunk_count <= 1:
        flags.append('V3_SINGLE_CHUNK_LARGE_RAW')
    if raw_field == 'native_detail.description' and raw_len >= 3000 and db_len <= max(800, int(raw_len * 0.15)):
        flags.append('V3_NATIVE_DETAIL_DESC_COLLAPSED')
    if doc_type in IMPORTANT_TYPES and raw_len >= 5000 and db_len <= max(750, int(raw_len * 0.10)):
        flags.append('V3_IMPORTANT_TYPE_COLLAPSED')
    if doc_type in IMPORTANT_TYPES and len(title) >= 80 and db_len <= max(600, len(title) * 3):
        flags.append('V3_IMPORTANT_TITLE_COLLAPSED')

    state = 'broken' if flags else ('healthy_short' if db_len < 5000 else ('healthy_medium' if db_len < 20000 else 'healthy_large'))
    return state, flags


# Load DB stats
db_stats = {}
with DB_STATS.open(encoding='utf-8') as f:
    for line in f:
        if line.strip():
            obj = json.loads(line)
            db_stats[obj['source_url']] = obj

# Load old broken uuid set and baseline heuristic comparison
old_rows = []
old_broken_uuid_rows = []
with OLD_AUDIT.open(newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        old_rows.append(row)
        if row.get('state') == 'broken':
            old_broken_uuid_rows.append(row['uuid'])
old_broken_uuid_set = set(old_broken_uuid_rows)

old_heuristic_counts = Counter()
old_heuristic_broken_uuids = set()
for row in old_rows:
    rec = {
        'raw_body_proxy_len': int(row.get('raw_body_proxy_len') or 0),
        'db_full_text_len': int(row.get('db_full_text_len') or 0),
        'chunk_count': int(row.get('chunk_count') or 0),
        'document_type': row.get('document_type') or '',
        'title': row.get('title') or '',
        'raw_body_field': row.get('raw_body_field') or '',
    }
    state, _ = classify(rec)
    old_heuristic_counts[state] += 1
    if state == 'broken':
        old_heuristic_broken_uuids.add(row['uuid'])

# Preindex normalized docs once
normalized_index = {}
for corpus_dir in sorted([p for p in CORPUS_ROOT.iterdir() if p.is_dir()]):
    for norm_json in corpus_dir.glob('normalized/**/document.json'):
        try:
            norm_obj = json.loads(norm_json.read_text(encoding='utf-8'))
        except Exception:
            continue
        uuid = norm_obj.get('id')
        if not uuid:
            continue
        normalized_index[(corpus_dir.name, uuid)] = (norm_json, norm_obj)

records = []
missing_db = 0
for corpus_dir in sorted([p for p in CORPUS_ROOT.iterdir() if p.is_dir()]):
    corpus = corpus_dir.name
    for raw_json in corpus_dir.glob('raw/documents/*/raw.json'):
        uuid = raw_json.parent.name
        norm_pair = normalized_index.get((corpus, uuid))
        if not norm_pair:
            continue
        norm_json, norm_obj = norm_pair
        try:
            raw_obj = json.loads(raw_json.read_text(encoding='utf-8'))
        except Exception:
            continue
        native_detail = raw_obj.get('native_detail') or {}
        data = raw_obj.get('data') or {}
        raw_body_field, raw_body = choose_raw_body(native_detail, data)
        raw_body_proxy_len = len(raw_body or '')
        raw_md_path = raw_json.parent / 'raw.md'
        raw_md_size = raw_md_path.stat().st_size if raw_md_path.exists() else 0
        raw_json_size = raw_json.stat().st_size if raw_json.exists() else 0
        norm_md_rel = (norm_obj.get('storage', {}) or {}).get('normalized_md', '')
        norm_md_path = corpus_dir / norm_md_rel if norm_md_rel else None
        normalized_md_size = norm_md_path.stat().st_size if norm_md_path and norm_md_path.exists() else 0
        source_url = norm_obj.get('source_url') or f'https://infohub.rs.ge/ka/workspace/document/{uuid}'
        stats = db_stats.get(source_url, {})
        if not stats:
            missing_db += 1
        rec = {
            'corpus': corpus,
            'uuid': uuid,
            'title': norm_obj.get('title') or (native_detail.get('name') if isinstance(native_detail, dict) else '') or '',
            'document_type': norm_obj.get('document_type') or '',
            'category': norm_obj.get('category') or '',
            'source_url': source_url,
            'raw_json_size': raw_json_size,
            'raw_md_size': raw_md_size,
            'raw_body_proxy_len': raw_body_proxy_len,
            'raw_body_field': raw_body_field,
            'normalized_md_size': normalized_md_size,
            'normalized_text_len': int(stats.get('db_full_text_len') or 0),
            'db_full_text_len': int(stats.get('db_full_text_len') or 0),
            'chunk_count': int(stats.get('chunk_count') or 0),
            'embedded_chunk_count': int(stats.get('embedded_chunk_count') or 0),
        }
        state, flags = classify(rec)
        rec['state'] = state
        rec['flags'] = ';'.join(flags)
        records.append(rec)

records.sort(key=lambda r: (r['corpus'], r['uuid']))
state_counts = Counter(r['state'] for r in records)
flag_counts = Counter()
by_corpus = defaultdict(Counter)
by_document_type = Counter()
broken_top = []
current_broken_uuid_set = set()
for r in records:
    by_corpus[r['corpus']][r['state']] += 1
    if r['state'] == 'broken':
        by_document_type[r['document_type'] or '(blank)'] += 1
        current_broken_uuid_set.add(r['uuid'])
        broken_top.append({
            'uuid': r['uuid'],
            'corpus': r['corpus'],
            'document_type': r['document_type'],
            'title': r['title'],
            'source_url': r['source_url'],
            'raw_body_proxy_len': r['raw_body_proxy_len'],
            'db_full_text_len': r['db_full_text_len'],
            'chunk_count': r['chunk_count'],
            'flags': r['flags'].split(';') if r['flags'] else [],
        })
        for flag in (r['flags'].split(';') if r['flags'] else []):
            if flag:
                flag_counts[flag] += 1

still_broken_old_set = sorted(current_broken_uuid_set & old_broken_uuid_set)
fixed_old_set = sorted(old_broken_uuid_set - current_broken_uuid_set)

csv_path = OUT_PREFIX.with_suffix('.csv')
with csv_path.open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'corpus','uuid','title','document_type','category','source_url','raw_json_size','raw_md_size',
        'raw_body_proxy_len','raw_body_field','normalized_md_size','normalized_text_len','db_full_text_len',
        'chunk_count','embedded_chunk_count','state','flags'
    ])
    writer.writeheader()
    writer.writerows(records)

summary = {
    'timestamp': TIMESTAMP,
    'total_docs_profiled': len(records),
    'state_counts': dict(state_counts),
    'flag_counts': dict(flag_counts),
    'by_corpus': {k: dict(v) for k, v in sorted(by_corpus.items())},
    'by_document_type': dict(by_document_type),
    'missing_db_stats': missing_db,
    'old_audit_reference': {
        'old_broken_rows': len(old_broken_uuid_rows),
        'old_broken_unique_uuids': len(old_broken_uuid_set),
        'heuristic_broken_on_old_csv': old_heuristic_counts.get('broken', 0),
        'heuristic_overlap_with_old_broken_unique': len(old_heuristic_broken_uuids & old_broken_uuid_set),
    },
    'repair_effect': {
        'current_broken_unique_uuids': len(current_broken_uuid_set),
        'old_broken_unique_uuids_still_broken': len(still_broken_old_set),
        'old_broken_unique_uuids_fixed': len(fixed_old_set),
    },
    'broken_top100': broken_top[:100],
}
json_path = OUT_PREFIX.with_suffix('.json')
json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

md_lines = [
    '# Invariant Audit v3 Post-Reindex',
    '',
    f'Timestamp: {TIMESTAMP}',
    '',
    f'- total_docs_profiled: {len(records)}',
]
for k, v in state_counts.most_common():
    md_lines.append(f'- {k}: {v}')
md_lines += [
    '',
    '## Repair effect vs old broken set',
    f'- old_broken_unique_uuids: {len(old_broken_uuid_set)}',
    f'- old_broken_unique_uuids_still_broken: {len(still_broken_old_set)}',
    f'- old_broken_unique_uuids_fixed: {len(fixed_old_set)}',
    '',
    '## Flag counts',
]
for k, v in flag_counts.most_common():
    md_lines.append(f'- {k}: {v}')
md_lines += ['', '## Broken by corpus']
for corpus, counts in sorted(by_corpus.items()):
    if counts.get('broken'):
        md_lines.append(f'- {corpus}: {counts.get("broken", 0)}')
md_lines += ['', '## Broken by type']
for k, v in by_document_type.most_common():
    md_lines.append(f'- {k}: {v}')
md_path = OUT_PREFIX.with_suffix('.md')
md_path.write_text('\n'.join(md_lines) + '\n', encoding='utf-8')

print(json.dumps({
    'csv': str(csv_path),
    'json': str(json_path),
    'md': str(md_path),
    'total_docs_profiled': len(records),
    'state_counts': dict(state_counts),
    'repair_effect': summary['repair_effect'],
    'missing_db_stats': missing_db,
}, ensure_ascii=False, indent=2))
