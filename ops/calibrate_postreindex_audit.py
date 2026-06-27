import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('/root/infohub')
AUDIT_OLD = ROOT / 'audits' / 'invariant_audit_v3_20260410_214438.csv'
AUDIT_NEW = ROOT / 'audits' / 'invariant_audit_v3_postreindex_20260418_071801.csv'
OUT = ROOT / 'audits' / 'invariant_audit_v3_postreindex_calibrated_20260418_2ndpass.json'


def parse_flags(s):
    if not s:
        return []
    return [x for x in s.split(';') if x]

old_by_uuid = {}
old_rows = []
with AUDIT_OLD.open(newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        old_rows.append(row)
        old_by_uuid.setdefault(row['uuid'], []).append(row)

new_by_uuid = {}
with AUDIT_NEW.open(newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        new_by_uuid.setdefault(row['uuid'], []).append(row)

old_broken_uuids = sorted({r['uuid'] for r in old_rows if r['state'] == 'broken'})

residuals = []
severity_counts = Counter()
by_corpus = Counter()
by_type = Counter()
flag_counts = Counter()

for uuid in old_broken_uuids:
    oldr = old_by_uuid[uuid][0]
    newr = (new_by_uuid.get(uuid) or [None])[0]
    if not newr:
        continue
    raw_len = int(newr['raw_body_proxy_len'] or 0)
    db_len = int(newr['db_full_text_len'] or 0)
    chunks = int(newr['chunk_count'] or 0)
    flags = parse_flags(newr['flags'])
    ratio = (db_len / raw_len) if raw_len else 1.0

    severe = False
    medium = False
    reason = []

    if raw_len >= 50000 and db_len <= 5000:
        severe = True
        reason.append('raw50k_to_text<=5k')
    if raw_len >= 20000 and db_len <= 2000:
        severe = True
        reason.append('raw20k_to_text<=2k')
    if raw_len >= 10000 and db_len <= 1000:
        severe = True
        reason.append('raw10k_to_text<=1k')
    if raw_len >= 5000 and chunks <= 1:
        severe = True
        reason.append('single_chunk_large_raw')
    if raw_len >= 5000 and ratio < 0.10:
        medium = True
        reason.append('ratio<10pct_large_raw')
    if 'V3_NATIVE_DETAIL_DESC_COLLAPSED' in flags and raw_len >= 3000 and db_len <= max(800, int(raw_len * 0.15)):
        medium = True
        reason.append('native_detail_desc_collapsed')

    # important-title-only noise should not count as true residual by itself
    if severe:
        severity = 'severe'
    elif medium:
        severity = 'medium'
    else:
        severity = 'resolved_or_low_confidence'

    if severity != 'resolved_or_low_confidence':
        rec = {
            'uuid': uuid,
            'corpus': newr['corpus'],
            'document_type': newr['document_type'],
            'title': newr['title'],
            'source_url': newr['source_url'],
            'raw_body_proxy_len': raw_len,
            'db_full_text_len': db_len,
            'chunk_count': chunks,
            'ratio': round(ratio, 4),
            'old_flags': parse_flags(oldr['flags']),
            'new_flags': flags,
            'severity': severity,
            'reason': reason,
        }
        residuals.append(rec)
        severity_counts[severity] += 1
        by_corpus[newr['corpus']] += 1
        by_type[newr['document_type'] or '(blank)'] += 1
        for fl in flags:
            flag_counts[fl] += 1

summary = {
    'old_broken_unique_uuids': len(old_broken_uuids),
    'residual_high_confidence_total': len(residuals),
    'severity_counts': dict(severity_counts),
    'by_corpus': dict(by_corpus),
    'by_document_type': dict(by_type),
    'flag_counts': dict(flag_counts),
    'top50': sorted(residuals, key=lambda r: (r['severity'] != 'severe', -r['raw_body_proxy_len'], r['uuid']))[:50],
}
OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
