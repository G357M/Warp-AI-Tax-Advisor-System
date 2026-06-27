#!/usr/bin/env python3
import argparse
import json
import math
import re
import statistics
import sys
import time
import socket
import urllib.error
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_QUERIES = [
    'Что говорит статья 166 Налогового кодекса?',
    'Что говорит статья 168 Налогового кодекса?',
    'Что говорит статья 169 Налогового кодекса?',
    'Что говорит статья 170 Налогового кодекса?',
    'Что говорит статья 172 Налогового кодекса?',
    'Что говорит статья 166 пункт 1 Налогового кодекса?',
    'Что говорит статья 168 пункт 1 Налогового кодекса?',
    'Что говорит статья 169 пункт 1 Налогового кодекса?',
    'Что говорит статья 170 пункт 1 Налогового кодекса?',
    'Что говорит ст. 172 п. 1 Налогового кодекса?',
    'Что говорит статья 169 часть 1 Налогового кодекса?',
    'Что говорит ст. 170 ч. 1 Налогового кодекса?',
    'Какие изменения в налоговом кодексе в 2026 году?',
    'Какие изменения по НДС в 2026 году?',
    'Какие изменения по налогу на прибыль в 2026 году?',
    'Какие изменения по таможне в 2026 году?',
    'Какие изменения по акцизу в 2026 году?',
    'Какие поправки в налоговом кодексе были приняты 1 апреля 2026 года?',
    'Какая ставка налога на имущество в Дманиси?',
    'Какая ставка налога на имущество в Тбилиси?',
    'Что в документе N1432?',
    'Как рассчитывается налог на имущество физлица?',
    'Какое решение по спору №19068/2/2023?',
]

PROFILE_QUERY_FILES = {
    'core': 'scripts/public_canary_queries_core.txt',
    'extended': 'scripts/public_canary_queries_extended.txt',
    'trimmed': 'scripts/public_canary_queries_trimmed.txt',
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run a public query stability watch and report 429 rate limits separately from weak answers.'
    )
    parser.add_argument('--url', default='http://localhost:8000/api/v1/public/query')
    parser.add_argument('--language', default='ru')
    parser.add_argument('--repeats', type=int, default=4)
    parser.add_argument('--delay-ms', type=int, default=0)
    parser.add_argument('--timeout', type=float, default=30.0)
    parser.add_argument('--queries-file', help='Optional text file with one query per line.')
    parser.add_argument('--profile', choices=['core', 'extended', 'trimmed'])
    parser.add_argument('--client-profile', choices=['auto', 'browser', 'api'], default='auto', help='Client shape for the request. auto=browser-like for external URLs, plain client for localhost.')
    parser.add_argument('--respect-rate-limit', action='store_true', default=None, help='Respect x-ratelimit-* headers. Defaults to on for external browser-like checks and off for localhost/API-client checks.')
    parser.add_argument('--ignore-rate-limit', action='store_true', help='Disable automatic rate-limit sleeps even for external URLs.')
    parser.add_argument('--user-agent', help='Optional User-Agent header override for public-edge/browser-like smoke checks.')
    parser.add_argument('--origin', help='Optional Origin header for browser-like public requests.')
    parser.add_argument('--referer', help='Optional Referer header for browser-like public requests.')
    parser.add_argument('--no-browser-like-defaults', action='store_true', help='Do not auto-apply browser-like headers for external public URLs.')
    return parser.parse_args()


def _trimmed_path_constraints(question_class: str, response_text: str, source_count: int) -> Dict[str, bool]:
    if question_class == 'named_document_lookup':
        return {
            'overlong_response': len(response_text) > 420,
            'source_shape_ok': source_count == 1,
        }
    if question_class == 'amendment_tracking':
        numbered_points = len(re.findall(r'(?m)^\s*\d+\.\s', response_text))
        return {
            'overlong_response': len(response_text) > 650,
            'source_shape_ok': source_count <= 2,
            'point_shape_ok': numbered_points <= 2,
        }
    return {
        'overlong_response': False,
        'source_shape_ok': True,
    }


def _load_queries(path: Optional[str]) -> List[str]:
    if not path:
        return list(DEFAULT_QUERIES)
    with open(path, 'r', encoding='utf-8') as fh:
        return [line.strip() for line in fh if line.strip() and not line.lstrip().startswith('#')]


def _resolve_queries_path(path: Optional[str], profile: Optional[str]) -> Optional[str]:
    if path:
        return path
    if profile:
        return PROFILE_QUERY_FILES[profile]
    return None


def _post_json(
    url: str,
    payload: Dict[str, Any],
    timeout: float,
    user_agent: Optional[str] = None,
    origin: Optional[str] = None,
    referer: Optional[str] = None,
) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if user_agent:
        headers['User-Agent'] = user_agent
    if origin:
        headers['Origin'] = origin
    if referer:
        headers['Referer'] = referer
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method='POST',
    )
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8', errors='replace')
            elapsed = round(time.time() - start, 3)
            body = json.loads(raw) if raw.strip() else {}
            return {
                'http_status': response.status,
                'elapsed_s': elapsed,
                'body': body,
                'headers': dict(response.headers.items()),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        elapsed = round(time.time() - start, 3)
        try:
            body = json.loads(raw) if raw.strip() else {}
        except Exception:
            body = {'raw_body': raw[:500]}
        return {
            'http_status': exc.code,
            'elapsed_s': elapsed,
            'body': body,
            'headers': dict(exc.headers.items()) if exc.headers else {},
        }
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionResetError, OSError) as exc:
        elapsed = round(time.time() - start, 3)
        return {
            'http_status': None,
            'elapsed_s': elapsed,
            'body': {'transport_error': str(exc)},
            'headers': {},
        }


def _is_external_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https'):
        return False
    return host not in ('', 'localhost', '127.0.0.1', '::1')


def _resolve_request_profile(args: argparse.Namespace) -> Tuple[Optional[str], Optional[str], Optional[str], bool, str]:
    external = _is_external_url(args.url)
    parsed = urllib.parse.urlparse(args.url)
    origin_base = f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else None

    effective_client_profile = args.client_profile
    if effective_client_profile == 'auto':
        effective_client_profile = 'browser' if external else 'api'

    user_agent = args.user_agent
    origin = args.origin
    referer = args.referer

    if effective_client_profile == 'browser' and external and not args.no_browser_like_defaults:
        user_agent = user_agent or 'Mozilla/5.0'
        origin = origin or origin_base
        referer = referer or (origin_base.rstrip('/') + '/' if origin_base else None)

    if args.ignore_rate_limit:
        respect_rate_limit = False
    elif args.respect_rate_limit is not None:
        respect_rate_limit = args.respect_rate_limit
    else:
        respect_rate_limit = external and effective_client_profile == 'browser'

    return user_agent, origin, referer, respect_rate_limit, effective_client_profile


def _contains_markdown_noise(text: str) -> bool:
    if not text:
        return False
    if re.search(r"\*\*.*?\*\*", text):
        return True
    if re.search(r"__.*?__", text):
        return True
    if re.search(r"\[[^\]]+\]\((https?://[^)]+)\)", text):
        return True
    return False


def _infer_question_class(query: str, body: Dict[str, Any]) -> str:
    explicit = (((body.get('_rag_v2') or {}).get('question_class')) or '').strip()
    if explicit:
        return explicit

    q = (query or '').lower()
    if 'спору №' in q or 'спор №' in q:
        return 'dispute_practice'
    if 'что в документе' in q:
        return 'named_document_lookup'
    if ('изменени' in q or 'поправк' in q) and ('кодекс' in q or 'ндс' in q or 'акциз' in q or 'тамож' in q or 'прибыл' in q):
        return 'amendment_tracking'
    if 'тбилиси' in q or 'дманиси' in q or 'гурджаани' in q:
        return 'local_regulation_lookup'
    if 'статья' in q or 'ст. ' in q:
        return 'canonical_law_lookup'
    return ''


def _classify_response(query: str, attempt: int, result: Dict[str, Any], client_profile: str) -> Dict[str, Any]:
    status = result['http_status']
    body = result.get('body') or {}
    headers = result.get('headers', {}) or {}
    response_text = body.get('response') or ''
    sources = body.get('sources') or []
    source_title = ((sources or [{}])[0].get('metadata', {}) or {}).get('title')
    source_titles = [((item.get('metadata') or {}).get('title') or '').strip() for item in sources]
    source_titles = [title for title in source_titles if title]
    unique_source_titles = list(dict.fromkeys(source_titles))
    question_class = _infer_question_class(query, body)
    source_count = len(sources)
    duplicate_sources = max(0, len(source_titles) - len(unique_source_titles))
    markdown_noise = _contains_markdown_noise(response_text)
    source_mentions = len(re.findall(r"Источник:", response_text, re.IGNORECASE))
    trailing_source_line = bool(re.search(r"\n+Источник:.*Источник:", response_text, re.IGNORECASE | re.DOTALL))
    grounded_no_evidence = bool(((body.get('_rag_v2') or {}).get('grounded_no_evidence')))
    trimmed_constraints = _trimmed_path_constraints(question_class, response_text, source_count)
    canonical_clean = question_class != 'canonical_law_lookup' or source_count == 1
    plain_text_clean = not markdown_noise and not trailing_source_line and source_mentions <= 1
    rate_limited = status == 429
    raw_body = ((body.get('raw_body') or '') if isinstance(body, dict) else '')
    policy_block = status == 403 and 'error code: 1010' in raw_body.lower()
    has_enough_grounding = bool(source_title) or grounded_no_evidence
    content_success = (
        status == 200
        and (bool(body.get('retrieved_count')) or grounded_no_evidence)
        and bool(response_text.strip())
        and 'нет информации' not in response_text.lower()
        and 'недостаточно' not in response_text.lower()
        and has_enough_grounding
        and plain_text_clean
        and canonical_clean
        and duplicate_sources == 0
        and not trimmed_constraints.get('overlong_response', False)
        and trimmed_constraints.get('source_shape_ok', True)
        and trimmed_constraints.get('point_shape_ok', True)
    )
    weak_answer = status == 200 and not content_success
    expected_outcome_ok = content_success if client_profile == 'browser' else policy_block
    row = {
        'query': query,
        'attempt': attempt,
        'http_status': status,
        'elapsed_s': result['elapsed_s'],
        'rate_limited': rate_limited,
        'success': content_success,
        'client_profile': client_profile,
        'policy_block': policy_block,
        'expected_outcome_ok': expected_outcome_ok,
        'weak_answer': weak_answer,
        'retrieved_count': body.get('retrieved_count'),
        'has_response': bool(response_text.strip()),
        'has_insufficient': ('нет информации' in response_text.lower() or 'недостаточно' in response_text.lower()),
        'source_title': source_title,
        'source_count': source_count,
        'duplicate_sources': duplicate_sources,
        'source_mentions': source_mentions,
        'markdown_noise': markdown_noise,
        'trailing_source_line': trailing_source_line,
        'question_class': question_class,
        'grounded_no_evidence': grounded_no_evidence,
        'overlong_response': trimmed_constraints.get('overlong_response', False),
        'trimmed_source_shape_ok': trimmed_constraints.get('source_shape_ok', True),
        'trimmed_point_shape_ok': trimmed_constraints.get('point_shape_ok', True),
        'response_preview': response_text[:160],
        'rate_limit_remaining': headers.get('x-ratelimit-remaining'),
        'rate_limit_reset': headers.get('x-ratelimit-reset'),
    }
    if status != 200 and not rate_limited:
        row['error_body'] = body
    return row


def _p95(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, int(len(ordered) * 0.95) - 1)
    return round(ordered[index], 3)


def _sleep_until_reset(row: Dict[str, Any]) -> None:
    reset_raw = row.get('rate_limit_reset')
    if not reset_raw:
        return
    try:
        reset_ts = int(reset_raw)
    except Exception:
        return
    wait_s = max(1, reset_ts - math.floor(time.time()) + 1)
    time.sleep(wait_s)


def _should_preemptive_wait(row: Dict[str, Any]) -> bool:
    try:
        remaining = row.get('rate_limit_remaining')
        return row.get('http_status') == 200 and remaining is not None and int(remaining) <= 0
    except Exception:
        return False


def main() -> int:
    args = _parse_args()
    queries = _load_queries(_resolve_queries_path(args.queries_file, args.profile))
    rows: List[Dict[str, Any]] = []
    user_agent, origin, referer, respect_rate_limit, client_profile = _resolve_request_profile(args)

    for query in queries:
        for attempt in range(1, args.repeats + 1):
            result = _post_json(
                args.url,
                {'query': query, 'language': args.language},
                timeout=args.timeout,
                user_agent=user_agent,
                origin=origin,
                referer=referer,
            )
            row = _classify_response(query, attempt, result, client_profile)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if respect_rate_limit and (row['rate_limited'] or _should_preemptive_wait(row)):
                _sleep_until_reset(row)
            if args.delay_ms > 0:
                time.sleep(args.delay_ms / 1000)

    summary = []
    for query in queries:
        items = [row for row in rows if row['query'] == query]
        ok_items = [row for row in items if row['http_status'] == 200]
        latencies = [row['elapsed_s'] for row in ok_items]
        summary.append({
            'query': query,
            'attempts': len(items),
            'successes': sum(1 for row in items if row['success']),
            'expected_outcome_ok': sum(1 for row in items if row['expected_outcome_ok']),
            'policy_blocks': sum(1 for row in items if row['policy_block']),
            'rate_limited': sum(1 for row in items if row['rate_limited']),
            'http_errors': sum(1 for row in items if row['http_status'] not in (200, 429, None)),
            'transport_errors': sum(1 for row in items if row['http_status'] is None),
            'weak_answers': sum(1 for row in items if row['weak_answer']),
            'avg_latency_s': round(statistics.mean(latencies), 3) if latencies else None,
            'p95_latency_s': _p95(latencies),
            'max_latency_s': max(latencies) if latencies else None,
        })

    report = {
        'client_profile': client_profile,
        'total_queries': len(queries),
        'repeats': args.repeats,
        'delay_ms': args.delay_ms,
        'total_runs': len(rows),
        'summary': summary,
        'overall': {
            'successes': sum(1 for row in rows if row['success']),
            'expected_outcome_ok': sum(1 for row in rows if row['expected_outcome_ok']),
            'policy_blocks': sum(1 for row in rows if row['policy_block']),
            'rate_limited': sum(1 for row in rows if row['rate_limited']),
            'http_errors': sum(1 for row in rows if row['http_status'] not in (200, 429, None)),
            'transport_errors': sum(1 for row in rows if row['http_status'] is None),
            'weak_answers': sum(1 for row in rows if row['weak_answer']),
        },
    }
    print('===SUMMARY===')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
