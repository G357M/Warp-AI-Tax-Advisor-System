#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

TOOLS_ROOT = Path('/root/infohub/corpus-tools')
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from export_pipeline.infohub_exporter import InfohubNormalizer  # type: ignore
from export_pipeline.infohub_native_api import (  # type: ignore
    InfohubNativeApiClient,
    build_source_url,
    native_detail_to_raw_payload,
)

ROOT = Path('/root/infohub')
AUDIT_OLD = ROOT / 'audits' / 'invariant_audit_v3_20260410_214438.csv'
AUDIT_NEW = ROOT / 'audits' / 'invariant_audit_v3_postreindex_20260418_071801.csv'
STATE_DIR = ROOT / 'state'
LOG_PATH = ROOT / 'logs' / 'reexport-residual.log'
COMPLETED_PATH = STATE_DIR / 'reexport-residual-completed.txt'
STATE_PATH = STATE_DIR / 'reexport-residual-state.json'
RESIDUAL_JSON = ROOT / 'audits' / 'residual_high_confidence_20260418.json'
RESIDUAL_CSV = ROOT / 'audits' / 'residual_high_confidence_20260418.csv'
SELECTED_JSON_DIR = STATE_DIR / 'residual-selected-json'
CORPUS_ROOT = ROOT / 'corpus'


def log(msg: str) -> None:
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def parse_flags(s: str | None) -> List[str]:
    if not s:
        return []
    return [x for x in s.split(';') if x]


def load_completed() -> set[str]:
    if not COMPLETED_PATH.exists():
        return set()
    return {line.strip() for line in COMPLETED_PATH.read_text(encoding='utf-8').splitlines() if line.strip()}


def append_completed(uuid: str) -> None:
    COMPLETED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COMPLETED_PATH.open('a', encoding='utf-8') as f:
        f.write(uuid + '\n')


def save_state(payload: Dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_residuals() -> List[Dict]:
    old_by_uuid: Dict[str, List[Dict[str, str]]] = {}
    old_rows: List[Dict[str, str]] = []
    with AUDIT_OLD.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            old_rows.append(row)
            old_by_uuid.setdefault(row['uuid'], []).append(row)

    new_by_uuid: Dict[str, List[Dict[str, str]]] = {}
    with AUDIT_NEW.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            new_by_uuid.setdefault(row['uuid'], []).append(row)

    old_broken_uuids = sorted({r['uuid'] for r in old_rows if r['state'] == 'broken'})
    residuals: List[Dict] = []

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
        reason: List[str] = []

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

        if severe:
            severity = 'severe'
        elif medium:
            severity = 'medium'
        else:
            severity = 'resolved_or_low_confidence'

        if severity == 'resolved_or_low_confidence':
            continue

        residuals.append({
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
        })

    residuals.sort(key=lambda r: (r['severity'] != 'severe', -r['raw_body_proxy_len'], r['uuid']))
    RESIDUAL_JSON.write_text(json.dumps(residuals, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with RESIDUAL_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=[
            'uuid', 'severity', 'corpus', 'document_type', 'title', 'source_url',
            'raw_body_proxy_len', 'db_full_text_len', 'chunk_count', 'ratio', 'reason', 'new_flags'
        ])
        w.writeheader()
        for r in residuals:
            w.writerow({
                **{k: r[k] for k in ['uuid', 'severity', 'corpus', 'document_type', 'title', 'source_url', 'raw_body_proxy_len', 'db_full_text_len', 'chunk_count', 'ratio']},
                'reason': ';'.join(r['reason']),
                'new_flags': ';'.join(r['new_flags']),
            })
    return residuals


def load_raw_doc_info(corpus: str, uuid: str) -> Tuple[int | None, str | None, str | None]:
    raw_json = CORPUS_ROOT / corpus / 'raw' / 'documents' / uuid / 'raw.json'
    if not raw_json.exists():
        return None, None, None
    obj = json.loads(raw_json.read_text(encoding='utf-8'))
    detail = obj.get('native_detail') or {}
    doc_id = detail.get('id')
    species = detail.get('species')
    source_url = (obj.get('data') or {}).get('metadata', {}).get('sourceUrl') or build_source_url(detail)
    return doc_id, species, source_url


def main() -> int:
    residuals = load_residuals()
    total = len(residuals)
    by_corpus = Counter(r['corpus'] for r in residuals)
    by_severity = Counter(r['severity'] for r in residuals)
    completed = load_completed()
    remaining_rows = [row for row in residuals if row['uuid'] not in completed]
    client = InfohubNativeApiClient(language_code='ka')
    normalizers: Dict[str, InfohubNormalizer] = {}
    selected_json_paths: Dict[str, set[str]] = defaultdict(set)
    ok = 0
    failed = 0
    started_at = time.time()

    log(f'start total_residual={total} already_completed={len(completed)} remaining={len(remaining_rows)} by_corpus={dict(by_corpus)} by_severity={dict(by_severity)}')
    save_state({
        'status': 'running',
        'total_residual': total,
        'completed_count': len(completed),
        'remaining_count': len(remaining_rows),
        'ok_this_run': 0,
        'failed_this_run': 0,
        'by_corpus': dict(by_corpus),
        'by_severity': dict(by_severity),
        'last_uuid': None,
        'last_corpus': None,
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started_at)),
        'residual_json': str(RESIDUAL_JSON),
        'residual_csv': str(RESIDUAL_CSV),
    })

    for idx, row in enumerate(remaining_rows, start=1):
        uuid = row['uuid']
        corpus = row['corpus']
        try:
            doc_id, species, source_url = load_raw_doc_info(corpus, uuid)
            if not doc_id:
                raise RuntimeError('missing raw doc id')
            detail = client.get_document_details(doc_id)
            source_url = source_url or build_source_url(detail)
            raw_payload = native_detail_to_raw_payload(detail, source_url=source_url)
            output_dir = CORPUS_ROOT / corpus
            norm = normalizers.get(corpus)
            if norm is None:
                norm = InfohubNormalizer(output_dir)
                normalizers[corpus] = norm
            result = norm.export_document(
                source_url,
                raw_payload,
                method='native-api-reexport-residual-calibrated',
                listing_species=species or detail.get('species'),
            )
            normalized_json = result.storage.normalized_json
            if normalized_json:
                selected_json_paths[corpus].add(normalized_json)
            append_completed(uuid)
            completed.add(uuid)
            ok += 1
            if ok % 10 == 0 or idx == 1:
                elapsed = max(time.time() - started_at, 1)
                rate = ok / elapsed
                eta = int((len(remaining_rows) - idx) / rate) if rate > 0 else None
                log(f"ok idx={idx}/{len(remaining_rows)} uuid={uuid} severity={row['severity']} corpus={corpus} doc_id={doc_id} norm={normalized_json} rate_per_sec={rate:.2f} eta_sec={eta}")
            save_state({
                'status': 'running',
                'total_residual': total,
                'completed_count': len(completed),
                'remaining_count': total - len(completed),
                'ok_this_run': ok,
                'failed_this_run': failed,
                'last_uuid': uuid,
                'last_corpus': corpus,
                'last_doc_id': doc_id,
                'progress_in_this_run': f'{idx}/{len(remaining_rows)}',
                'selected_json_counts': {k: len(v) for k, v in selected_json_paths.items()},
                'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started_at)),
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
        except Exception as exc:
            failed += 1
            log(f'error idx={idx}/{len(remaining_rows)} uuid={uuid} corpus={corpus} error={exc}')
            save_state({
                'status': 'running',
                'total_residual': total,
                'completed_count': len(completed),
                'remaining_count': total - len(completed),
                'ok_this_run': ok,
                'failed_this_run': failed,
                'last_uuid': uuid,
                'last_corpus': corpus,
                'last_error': str(exc),
                'progress_in_this_run': f'{idx}/{len(remaining_rows)}',
                'selected_json_counts': {k: len(v) for k, v in selected_json_paths.items()},
                'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started_at)),
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
            continue

    SELECTED_JSON_DIR.mkdir(parents=True, exist_ok=True)
    selected_json_files = {}
    for corpus, rels in selected_json_paths.items():
        out = SELECTED_JSON_DIR / f'{corpus}.json'
        data = sorted(rels)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        selected_json_files[corpus] = str(out)

    elapsed = time.time() - started_at
    log(f'finished ok={ok} failed={failed} total_completed={len(completed)}/{total} elapsed_sec={int(elapsed)} selected_json_files={selected_json_files}')
    save_state({
        'status': 'finished',
        'total_residual': total,
        'completed_count': len(completed),
        'remaining_count': total - len(completed),
        'ok_this_run': ok,
        'failed_this_run': failed,
        'selected_json_files': selected_json_files,
        'elapsed_sec': int(elapsed),
        'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
