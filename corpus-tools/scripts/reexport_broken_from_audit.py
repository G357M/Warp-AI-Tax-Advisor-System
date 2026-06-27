#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
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

AUDIT_CSV = Path('/root/infohub/audits/invariant_audit_v3_20260410_214438.csv')
STATE_DIR = Path('/root/infohub/state')
COMPLETED_PATH = STATE_DIR / 'reexport-broken-completed.txt'
STATE_PATH = STATE_DIR / 'reexport-broken-state.json'
LOG_PATH = Path('/root/infohub/logs/reexport-broken.log')
CORPUS_ROOT = Path('/root/infohub/corpus')


def log(msg: str) -> None:
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


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


def load_broken_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with AUDIT_CSV.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('state') != 'broken':
                continue
            rows.append(row)
    return rows


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
    broken_rows = load_broken_rows()
    total = len(broken_rows)
    by_corpus = Counter(row['corpus'] for row in broken_rows)
    completed = load_completed()
    remaining_rows = [row for row in broken_rows if row['uuid'] not in completed]
    client = InfohubNativeApiClient(language_code='ka')
    normalizers: Dict[str, InfohubNormalizer] = {}
    ok = 0
    failed = 0
    started_at = time.time()

    log(f'start total_broken={total} already_completed={len(completed)} remaining={len(remaining_rows)} by_corpus={dict(by_corpus)}')
    save_state({
        'status': 'running',
        'total_broken': total,
        'completed_count': len(completed),
        'remaining_count': len(remaining_rows),
        'ok_this_run': 0,
        'failed_this_run': 0,
        'last_uuid': None,
        'last_corpus': None,
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started_at)),
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
                method='native-api-reexport-broken',
                listing_species=species or detail.get('species'),
            )
            append_completed(uuid)
            completed.add(uuid)
            ok += 1
            if ok % 25 == 0 or idx == 1:
                elapsed = max(time.time() - started_at, 1)
                rate = ok / elapsed
                eta = int((len(remaining_rows) - idx) / rate) if rate > 0 else None
                log(f'ok idx={idx}/{len(remaining_rows)} uuid={uuid} corpus={corpus} doc_id={doc_id} norm={result.storage.normalized_json} rate_per_sec={rate:.2f} eta_sec={eta}')
            save_state({
                'status': 'running',
                'total_broken': total,
                'completed_count': len(completed),
                'remaining_count': total - len(completed),
                'ok_this_run': ok,
                'failed_this_run': failed,
                'last_uuid': uuid,
                'last_corpus': corpus,
                'last_doc_id': doc_id,
                'progress_in_this_run': f'{idx}/{len(remaining_rows)}',
                'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started_at)),
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
        except Exception as exc:
            failed += 1
            log(f'error idx={idx}/{len(remaining_rows)} uuid={uuid} corpus={corpus} error={exc}')
            save_state({
                'status': 'running',
                'total_broken': total,
                'completed_count': len(completed),
                'remaining_count': total - len(completed),
                'ok_this_run': ok,
                'failed_this_run': failed,
                'last_uuid': uuid,
                'last_corpus': corpus,
                'last_error': str(exc),
                'progress_in_this_run': f'{idx}/{len(remaining_rows)}',
                'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started_at)),
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
            continue

    elapsed = time.time() - started_at
    log(f'finished ok={ok} failed={failed} total_completed={len(completed)}/{total} elapsed_sec={int(elapsed)}')
    save_state({
        'status': 'finished',
        'total_broken': total,
        'completed_count': len(completed),
        'remaining_count': total - len(completed),
        'ok_this_run': ok,
        'failed_this_run': failed,
        'elapsed_sec': int(elapsed),
        'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
