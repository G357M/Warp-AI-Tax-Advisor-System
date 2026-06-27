#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List

TOOLS_ROOT = Path('/root/infohub/corpus-tools')
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from export_pipeline.infohub_exporter import InfohubNormalizer  # type: ignore
from export_pipeline.infohub_native_api import build_source_url, native_detail_to_raw_payload  # type: ignore

ROOT = Path('/root/infohub')
CORPUS_ROOT = ROOT / 'corpus'
STATE_PATH = ROOT / 'state' / 'reparse-all-state.json'
LOG_PATH = ROOT / 'logs' / 'reparse-all.log'

CORPORA = [
    'live-native-legislative-news',
    'live-native-newdocument',
]


def log(msg: str) -> None:
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def save_state(payload: Dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def collect_raw_docs() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for corpus in CORPORA:
        for raw_json in sorted((CORPUS_ROOT / corpus / 'raw' / 'documents').glob('*/raw.json')):
            rows.append({'corpus': corpus, 'raw_json': str(raw_json)})
    return rows


def main() -> int:
    rows = collect_raw_docs()
    total = len(rows)
    by_corpus = Counter(r['corpus'] for r in rows)
    started = time.time()
    ok = 0
    failed = 0
    normalizers: Dict[str, InfohubNormalizer] = {}

    log(f'start total={total} by_corpus={dict(by_corpus)}')
    save_state({
        'status': 'running',
        'total': total,
        'completed_count': 0,
        'remaining_count': total,
        'ok': 0,
        'failed': 0,
        'by_corpus': dict(by_corpus),
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started)),
    })

    for idx, row in enumerate(rows, start=1):
        corpus = row['corpus']
        raw_json = Path(row['raw_json'])
        uuid = raw_json.parent.name
        try:
            obj = json.loads(raw_json.read_text(encoding='utf-8'))
            detail = obj.get('native_detail') or {}
            source_url = ((obj.get('data') or {}).get('metadata') or {}).get('sourceUrl') or build_source_url(detail)
            payload = native_detail_to_raw_payload(detail, source_url=source_url)
            norm = normalizers.get(corpus)
            if norm is None:
                norm = InfohubNormalizer(CORPUS_ROOT / corpus)
                normalizers[corpus] = norm
            result = norm.export_document(
                source_url,
                payload,
                method='native-api-reparse-all-from-raw-v2',
                listing_species=detail.get('species'),
            )
            ok += 1
            if ok == 1 or ok % 100 == 0:
                elapsed = max(1.0, time.time() - started)
                rate = ok / elapsed
                eta = int((total - idx) / rate) if rate > 0 else None
                log(f'ok idx={idx}/{total} uuid={uuid} corpus={corpus} norm={result.storage.normalized_json} rate_per_sec={rate:.2f} eta_sec={eta}')
        except Exception as exc:
            failed += 1
            log(f'error idx={idx}/{total} uuid={uuid} corpus={corpus} error={exc}')
        finally:
            save_state({
                'status': 'running',
                'total': total,
                'completed_count': ok + failed,
                'remaining_count': total - (ok + failed),
                'ok': ok,
                'failed': failed,
                'last_uuid': uuid,
                'last_corpus': corpus,
                'progress': f'{idx}/{total}',
                'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started)),
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })

    elapsed = int(time.time() - started)
    log(f'finished ok={ok} failed={failed} total={total} elapsed_sec={elapsed}')
    save_state({
        'status': 'finished',
        'total': total,
        'completed_count': ok + failed,
        'remaining_count': total - (ok + failed),
        'ok': ok,
        'failed': failed,
        'elapsed_sec': elapsed,
        'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    })
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
