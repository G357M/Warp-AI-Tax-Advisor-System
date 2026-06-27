#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import dotenv_values

ROOT = Path('/root/infohub')
TOOLS_ROOT = ROOT / 'corpus-tools'
BACKEND_ROOT = ROOT / 'backend'
for path in [str(TOOLS_ROOT), str(BACKEND_ROOT)]:
    if path not in sys.path:
        sys.path.insert(0, path)

from export_pipeline.infohub_exporter import InfohubNormalizer  # type: ignore
from export_pipeline.infohub_native_api import build_source_url  # type: ignore
from export_pipeline.scrapling_repair import build_scrapling_repaired_payload, needs_db_repair  # type: ignore

FULL_STATE_CSV = ROOT / 'full_corpus_state_20260410_200905.csv'
BROKEN_AUDIT_CSV = ROOT / 'audits' / 'invariant_audit_v3_postreindex_20260418_071801.csv'
CORPUS_ROOT = ROOT / 'corpus'
STATE_DIR = ROOT / 'state'
SELECTED_DIR = STATE_DIR / 'scrapling-repair-selected-json'
STATE_PATH = STATE_DIR / 'scrapling-repair-state.json'
REPORT_PATH = STATE_DIR / 'scrapling-repair-report.json'
LOG_PATH = ROOT / 'logs' / 'scrapling-repair.log'


def log(message: str) -> None:
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {message}'
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open('a', encoding='utf-8') as fh:
        fh.write(line + '\n')


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_suspicious_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with FULL_STATE_CSV.open(encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            classification = row.get('classification') or ''
            if classification.startswith('suspicious_'):
                rows.append({**row, 'classification': classification})
    return rows


def load_broken_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with BROKEN_AUDIT_CSV.open(encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if (row.get('state') or '') != 'broken':
                continue
            rows.append({**row, 'classification': 'broken'})
    return rows


def build_candidates(include_broken: bool, include_suspicious: bool) -> List[Dict[str, str]]:
    merged: Dict[Tuple[str, str], Dict[str, str]] = {}
    if include_suspicious:
        for row in load_suspicious_rows():
            merged[(row['corpus'], row['uuid'])] = row
    if include_broken:
        for row in load_broken_rows():
            key = (row['corpus'], row['uuid'])
            current = merged.get(key)
            if current is None or current.get('classification') != 'suspicious_shrink':
                merged[key] = row
    rows = sorted(merged.values(), key=lambda r: (r['corpus'], r['uuid']))
    return rows


def read_raw_doc(corpus: str, uuid: str) -> Dict:
    raw_path = CORPUS_ROOT / corpus / 'raw' / 'documents' / uuid / 'raw.json'
    return json.loads(raw_path.read_text(encoding='utf-8'))


def run_db_reindex(selected_by_corpus: Dict[str, List[str]]) -> Dict[str, Dict[str, object]]:
    results: Dict[str, Dict[str, object]] = {}
    for corpus, relpaths in selected_by_corpus.items():
        selected_path = SELECTED_DIR / f'{corpus}.json'
        cmd = [
            str(ROOT / '.venv-corpus' / 'bin' / 'python'),
            str(ROOT / 'corpus-tools' / 'scripts' / 'index_export_corpus.py'),
            '--corpus-dir',
            str(CORPUS_ROOT / corpus),
            '--selected-json',
            str(selected_path),
            '--write-db',
            '--force',
        ]
        env = dict(os.environ)
        cfg = dotenv_values(ROOT / '.env')
        env['PYTHONPATH'] = f"{BACKEND_ROOT}:{TOOLS_ROOT}:" + env.get('PYTHONPATH', '')
        env['SECRET_KEY'] = str(cfg.get('SECRET_KEY') or env.get('SECRET_KEY') or '')
        env['JWT_SECRET_KEY'] = str(cfg.get('JWT_SECRET_KEY') or env.get('JWT_SECRET_KEY') or '')
        postgres_password = str(cfg.get('POSTGRES_PASSWORD') or '')
        env['DATABASE_URL'] = env.get('DATABASE_URL') or f'postgresql://infohub_user:{postgres_password}@127.0.0.1:5432/infohub_ai'
        env['REDIS_URL'] = env.get('REDIS_URL') or 'redis://127.0.0.1:6379'
        env['DEBUG'] = 'false'
        proc = subprocess.run(cmd, cwd=str(BACKEND_ROOT), capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise RuntimeError(f'index_export_corpus failed for {corpus}: {proc.stderr or proc.stdout}')
        stdout = (proc.stdout or '').strip()
        json_start = stdout.find('{')
        if json_start < 0:
            raise RuntimeError(f'index_export_corpus returned no JSON for {corpus}: {stdout}')
        payload = json.loads(stdout[json_start:])
        results[corpus] = payload
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description='Repair broken/suspicious docs via Scrapling-audited reexport lane')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--skip-db-reindex', action='store_true')
    parser.add_argument('--broken-only', action='store_true')
    parser.add_argument('--suspicious-only', action='store_true')
    args = parser.parse_args()

    include_broken = not args.suspicious_only
    include_suspicious = not args.broken_only
    if not include_broken and not include_suspicious:
        raise SystemExit('nothing selected')

    candidates = build_candidates(include_broken=include_broken, include_suspicious=include_suspicious)
    if args.limit:
        candidates = candidates[: args.limit]

    selected_by_corpus: Dict[str, List[str]] = defaultdict(list)
    report_rows: List[Dict[str, object]] = []
    stats = Counter()
    normalizers: Dict[str, InfohubNormalizer] = {}
    started = time.time()

    log(f'start candidates={len(candidates)} include_broken={include_broken} include_suspicious={include_suspicious}')
    save_json(STATE_PATH, {
        'status': 'running',
        'total_candidates': len(candidates),
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started)),
    })

    for idx, row in enumerate(candidates, start=1):
        corpus = row['corpus']
        uuid = row['uuid']
        classification = row.get('classification') or 'unknown'
        try:
            raw = read_raw_doc(corpus, uuid)
            detail = raw.get('native_detail') or {}
            source_url = row.get('source_url') or (((raw.get('data') or {}).get('metadata') or {}).get('sourceUrl')) or build_source_url(detail)
            repaired_payload, diagnostics = build_scrapling_repaired_payload(detail, source_url=source_url)
            db_len = int(row.get('db_full_text_len') or 0)
            chunk_count = int(row.get('chunk_count') or 0)
            should_reindex, reason = needs_db_repair(
                db_full_text_len=db_len,
                repaired_markdown_len=int(diagnostics['repaired_markdown_len']),
                chunk_count=chunk_count,
                classification=classification,
            )
            if not should_reindex:
                stats['skipped_not_needed'] += 1
                continue

            norm = normalizers.get(corpus)
            if norm is None:
                norm = InfohubNormalizer(CORPUS_ROOT / corpus)
                normalizers[corpus] = norm

            result = norm.export_document(
                source_url,
                repaired_payload,
                method='native-api-scrapling-repair-v1',
                listing_species=detail.get('species'),
            )
            selected_by_corpus[corpus].append(result.storage.normalized_json)
            stats['selected_total'] += 1
            stats[f'selected_{classification}'] += 1
            if diagnostics.get('used_scrapling'):
                stats['used_scrapling'] += 1

            report_rows.append({
                'corpus': corpus,
                'uuid': uuid,
                'classification': classification,
                'source_url': source_url,
                'db_full_text_len': db_len,
                'chunk_count': chunk_count,
                'reindex_reason': reason,
                **diagnostics,
                'normalized_json': result.storage.normalized_json,
            })

            if stats['selected_total'] == 1 or stats['selected_total'] % 50 == 0:
                elapsed = max(time.time() - started, 1.0)
                rate = stats['selected_total'] / elapsed
                log(
                    f"ok idx={idx}/{len(candidates)} selected={stats['selected_total']} uuid={uuid} corpus={corpus} class={classification} "
                    f"used_scrapling={diagnostics['used_scrapling']} repaired_len={diagnostics['repaired_markdown_len']} db_len={db_len} rate_per_sec={rate:.2f}"
                )

            save_json(STATE_PATH, {
                'status': 'running',
                'total_candidates': len(candidates),
                'processed': idx,
                'selected_total': stats['selected_total'],
                'used_scrapling': stats['used_scrapling'],
                'skipped_not_needed': stats['skipped_not_needed'],
                'last_uuid': uuid,
                'last_corpus': corpus,
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
        except Exception as exc:
            stats['failed'] += 1
            log(f'error idx={idx}/{len(candidates)} uuid={uuid} corpus={corpus} class={classification} error={exc}')

    for corpus, relpaths in selected_by_corpus.items():
        unique_relpaths = sorted(set(relpaths))
        selected_by_corpus[corpus] = unique_relpaths
        save_json(SELECTED_DIR / f'{corpus}.json', unique_relpaths)

    db_results: Dict[str, Dict[str, object]] = {}
    if not args.skip_db_reindex and selected_by_corpus:
        log(f'db_reindex_start corpora={list(selected_by_corpus)} docs={sum(len(v) for v in selected_by_corpus.values())}')
        db_results = run_db_reindex(selected_by_corpus)
        log(f'db_reindex_done results={db_results}')

    elapsed = int(time.time() - started)
    report = {
        'stats': dict(stats),
        'selected_counts_by_corpus': {k: len(v) for k, v in selected_by_corpus.items()},
        'db_results': db_results,
        'rows': report_rows,
        'elapsed_sec': elapsed,
        'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    save_json(REPORT_PATH, report)
    save_json(STATE_PATH, {
        'status': 'finished',
        'stats': dict(stats),
        'selected_counts_by_corpus': {k: len(v) for k, v in selected_by_corpus.items()},
        'db_results': db_results,
        'elapsed_sec': elapsed,
        'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    })
    log(f'finished stats={dict(stats)} elapsed_sec={elapsed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
