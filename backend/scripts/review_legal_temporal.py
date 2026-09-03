#!/usr/bin/env python3
"""Build offline per-law expert dossiers or validate disjoint review batches.

No command connects to a database or changes public answers. With no command,
print the safety plan. Outputs must be new; raw evidence is never overwritten.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.backfill import BackfillValidationError, sha256_json
from legal_temporal.expert_review import (
    REVIEW_CONTRACT, ReviewValidationError, build_rows, load_evidence,
    read_review, review_document, validate_reviews,
)


def safety_plan():
    return {
        "contract": REVIEW_CONTRACT, "database_calls_allowed": False,
        "network_calls_allowed": False, "database_writes_allowed": False,
        "public_answer_routing_changed": False,
        "commands": ["build", "validate"],
        "output_kind": "non_executable_expert_proposals",
    }


def _write_new(path: Path, value: str) -> str:
    raw = value.encode("utf-8")
    # Exclusive creation with owner-only permissions from the very first byte.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        handle.write(raw)
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _check_new_output(bundle: Path, output: Path):
    if output.exists() or output.is_symlink():
        raise ReviewValidationError("output path already exists")
    root = bundle.resolve()
    resolved = output.resolve()
    if resolved == root or root in resolved.parents:
        raise ReviewValidationError("review output must be outside the source bundle")


def _md(value):
    # Source titles/excerpts are untrusted content, not Markdown/HTML commands.
    value = html.escape(str(value or ""), quote=True)
    for char in ("\\", "`", "*", "_", "[", "]", "(", ")", "#", "!", "|", "~"):
        value = value.replace(char, "\\" + char)
    return value


def _dossier(rows):
    lines = [
        "# Исторические изменения — экспертная проверка", "",
        "Это кандидаты, а не подтверждённые редакции закона. Отрывки — только подсказки для поиска.",
        "Откройте полный архивный текст и официальный источник; проверьте также переходные положения.",
        "Решения вносятся в соседний JSON только в объект decision. Инструкция: ../README.md.", "",
    ]
    for row in rows:
        evidence = row["evidence"]
        lines += [f"## {row['row_id']}", ""]
        for label, key in (("Изменяющий акт", "amendment_source"), ("Изменяемый акт", "target_source")):
            source = evidence[key]
            if source:
                lines += [
                    f"{label}: {_md(source['title'])}", "",
                    f"[Официальная карточка]({source['workspace_url']}) · "
                    f"[Полный сохранённый текст](../{source['normalized_text_file']})", "",
                    f"SHA-256 точных API bytes: `{source['content_sha256']}`", "",
                    f"Состояние источника: `{source['verification_mode']}`", "",
                ]
            else:
                lines += [f"{label}: не установлен.", ""]
        lines += [
            f"Статья-кандидат: {_md(evidence['article_ref'])}; действие: {_md(evidence['legacy_action'])}.", "",
            f"Дата принятия: {_md(evidence['adoption_date'])}; предполагаемое вступление: {_md(evidence['effective_date'])}.", "",
            f"Причина классификации: {_md(evidence['classification']['reason'])}.", "",
            f"Блокеры: {_md(', '.join(evidence['blockers']) or 'нет технических блокеров; нужна юридическая проверка')}.", "",
        ]
        for excerpt in evidence["navigation_excerpts"]:
            lines += ["Навигационный отрывок (не доказательство применимости):", ""]
            lines += ["> " + _md(line) for line in excerpt.splitlines()]
            lines.append("")
    return "\n".join(lines) + "\n"


INSTRUCTIONS = """# Проверка исторических изменений

Начните с INDEX.md: выберите закон и пакет. Не нужно проверять всю очередь сразу.
Пакет .md — читаемое досье, соседний .json — технический файл решений.
Полные тексты в sources/*.txt — воспроизведённая нормализация архивного снимка,
а не новая консолидированная редакция. Оригинальные API bytes остаются в исходном
защищённом backfill bundle; SHA-256 указан в каждой строке. Сайт может измениться
после снимка: расхождения требуют нового доказательного пакета, не правки evidence.

## Что проверять

1. Правильность пары изменяющий/изменяемый акт и конкретной статьи, части, пункта.
2. Содержание операции (добавление, замена, отмена), её пределы и исключения.
3. Вступление именно этого изменения в силу, отложенные даты и переходные нормы.
4. Подтверждение точными цитатами из полного сохранённого изменяющего акта.

## Как передать решения

Можно сообщить оператору row_id, решение, цитаты, обоснование и реальное время
проверки. Оператор перенесёт их в JSON без изменения evidence. Технический файл
самому редактировать необязательно. Имя эксперта и время нельзя выдумывать.

В JSON меняется только decision:

- state: pending (не проверено), confirm (подтвердить кандидата), correct
  (предложить исправление), reject (отклонить), defer (нужны дополнительные данные).
- reviewer: полное имя реального эксперта.
- reviewed_at_utc: действительное время проверки, YYYY-MM-DDTHH:MM:SSZ, UTC.
- rationale: юридическое обоснование, минимум 20 знаков.
- evidence_locator: конкретные статья/часть/пункт изменяющего акта и переходная норма.
- operative_quote: точная цитата об изменении, минимум 20 знаков.
- effective_date_quote: точная цитата о вступлении в силу, минимум 20 знаков.
- proposed_correction: null, кроме correct. Для correct объект содержит только
  target_legacy_document_id (из источников исходного bundle), article_ref
  (например 5 или 5-1), operation_type (add/replace/repeal), effective_date
  (YYYY-MM-DD). Это предложение, не исполняемая замена нормы.

Для confirm/correct обе цитаты обязательны и должны дословно встречаться в
архивном тексте. Для reject обязательны имя, время, обоснование и evidence_locator;
для defer — имя, время и обоснование. У pending остальные поля остаются пустыми.
Нельзя confirm при drift, отсутствии цели/даты или неоднозначной классификации.
correct/reject/defer не снимают блокировку источника автоматически.

Валидатор принимает один или несколько непересекающихся пакетов; можно оставить
только проверенные строки. Пропущенные строки учитываются отдельно и не считаются
проверенными. Один неверный ряд блокирует весь экспорт предложений. Не передавайте
две версии одной строки одновременно: выберите актуальную вручную.

Валидатор проверяет формат и привязку доказательств, но не способен удостоверить
личность эксперта, применимость цитаты или правильность юридического вывода.
Даже confirm требует независимой проверки и реконструкции перед публикацией.
Ни build, ни validate не пишут в БД, не создают редакции и не меняют ответы сайта.
"""


def build_packet(bundle: Path, pin: str, output: Path, batch_size: int = 50):
    if not 1 <= batch_size <= 100:
        raise ReviewValidationError("batch size must be 1..100")
    _check_new_output(bundle, output)
    output = output.resolve()
    manifest, texts = load_evidence(bundle, pin)
    rows = build_rows(manifest, texts)
    grouped = defaultdict(list)
    for row in rows:
        evidence = row["evidence"]
        target_id = (evidence["target_source"] or {}).get("legacy_document_id", "unresolved")
        grouped[(target_id, evidence["lane"])].append(row)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for child in ("batches", "sources"):
        (output / child).mkdir(mode=0o700)
    for doc_id, text in sorted(texts.items()):
        _write_new(output / "sources" / f"{doc_id}.txt", text)
    batches = []
    index = ["# Очередь экспертной проверки по законам", "", "Инструкция: [README.md](README.md).", ""]
    target_totals = Counter()
    for (target_id, _lane), group in grouped.items():
        target_totals[target_id] += len(group)
    lane_order = {"expert_confirmation": 0, "candidate_resolution": 1, "source_reconciliation": 2}
    ordered = sorted(grouped.items(), key=lambda entry: (
        entry[0][0] == "unresolved", -target_totals[entry[0][0]],
        entry[0][0], lane_order[entry[0][1]],
    ))
    for (target_id, lane), group in ordered:
        target = group[0]["evidence"]["target_source"]
        title = target["title"] if target else "Изменяемый акт не установлен"
        index += [f"## {_md(title)}", "", f"Направление: `{lane}`. Строк: {len(group)}.", ""]
        for offset in range(0, len(group), batch_size):
            subset = group[offset:offset + batch_size]
            batch_id = "BATCH-" + sha256_json([r["row_id"] for r in subset])[:24]
            review_file = f"batches/{batch_id}.json"
            dossier_file = f"batches/{batch_id}.md"
            file_sha = _write_new(output / review_file, _json(review_document(manifest, subset)))
            dossier_sha = _write_new(output / dossier_file, _dossier(subset))
            batches.append({
                "batch_id": batch_id, "target_legacy_document_id": target_id,
                "target_title": title, "lane": lane, "rows": len(subset),
                "review_file": review_file, "review_sha256": file_sha,
                "dossier_file": dossier_file, "dossier_sha256": dossier_sha,
            })
            index += [f"- [Досье {offset // batch_size + 1}]({dossier_file}) — {len(subset)} строк; [решения JSON]({review_file})."]
        index.append("")
    summary = safety_plan() | {
        "manifest_sha256": pin, "review_rows": len(rows), "sources": len(texts),
        "target_laws": len({key[0] for key in grouped} - {"unresolved"}),
        "lanes": dict(sorted(Counter(r["evidence"]["lane"] for r in rows).items())),
        "batches": len(batches), "batch_size": batch_size,
    }
    _write_new(output / "README.md", INSTRUCTIONS)
    _write_new(output / "INDEX.md", "\n".join(index) + "\n")
    _write_new(output / "summary.json", _json(summary))
    # Completion marker written last; failed exports remain visibly incomplete.
    _write_new(output / "index.json", _json({"summary": summary, "batches": batches}))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    for command in ("build", "validate"):
        child = sub.add_parser(command)
        child.add_argument("--bundle", type=Path, required=True)
        child.add_argument("--expected-manifest-sha256", required=True)
        child.add_argument("--output", type=Path, required=command == "build")
        if command == "build":
            child.add_argument("--batch-size", type=int, default=50)
        else:
            selected = child.add_mutually_exclusive_group(required=True)
            selected.add_argument("--reviews", type=Path, nargs="+")
            selected.add_argument("--review-dir", type=Path)
    args = parser.parse_args(argv)
    if args.command is None:
        report = safety_plan()
    elif args.command == "build":
        report = build_packet(args.bundle, args.expected_manifest_sha256, args.output, args.batch_size)
    else:
        if args.output:
            _check_new_output(args.bundle, args.output)
        if args.review_dir:
            if args.review_dir.is_symlink() or not args.review_dir.is_dir():
                raise ReviewValidationError("review-dir must be a regular directory")
            paths = sorted(args.review_dir.glob("BATCH-*.json"))
        else:
            paths = args.reviews
        if not paths or len(paths) > 500:
            raise ReviewValidationError("provide 1..500 review batches")
        if sum(p.stat().st_size for p in paths) > 128 * 1024 * 1024:
            raise ReviewValidationError("combined review inputs exceed 128 MiB")
        manifest, texts = load_evidence(args.bundle, args.expected_manifest_sha256)
        result = validate_reviews(manifest, texts, [read_review(p) for p in paths])
        report = {k: v for k, v in result.items() if k != "proposals"}
        report["proposal_count"] = len(result["proposals"])
        if args.output and not result["errors"]:
            _write_new(args.output, _json(result))
    print("LEGAL_TEMPORAL_EXPERT_REVIEW=" + json.dumps(report, sort_keys=True))
    return 1 if report.get("error_count") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BackfillValidationError, ReviewValidationError, OSError) as exc:
        print(f"LEGAL_TEMPORAL_EXPERT_REVIEW_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)
