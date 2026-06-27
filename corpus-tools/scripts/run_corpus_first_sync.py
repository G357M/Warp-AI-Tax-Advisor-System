#!/usr/bin/env python3
"""Host-side corpus-first sync runner.

Flow per tick:
1. Pick next species/page from state.
2. Export one native-API page into a persistent corpus directory.
3. Build a minimal staging corpus for just the exported documents.
4. Copy staging corpus into the backend container.
5. Index only those selected documents into DB + embeddings.
6. Persist run log + advance state.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class SyncRunResult:
    ts: str
    species: str
    page: int
    page_size: int
    exported_count: int
    corpus_dir: str
    stage_dir: str
    before_counts: Dict[str, Any]
    after_counts: Dict[str, Any]
    pilot_result: Dict[str, Any]
    index_result: Dict[str, Any]
    next_state: Dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one corpus-first sync tick")
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--corpus-root", required=True)
    parser.add_argument("--staging-root", required=True)
    parser.add_argument("--container", default="infohub-backend")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--species-order", default="NewDocument,LegislativeNews")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def load_state(path: Path, species_order: List[str]) -> Dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "species_order": species_order,
        "next_species_index": 0,
        "pages": {species: 1 for species in species_order},
    }


def species_slug(species: str) -> str:
    mapping = {
        "NewDocument": "newdocument",
        "LegislativeNews": "legislative-news",
        "Bill": "bill",
    }
    return mapping.get(species, species.lower())


def run_json(cmd: List[str], cwd: Path | None = None) -> Dict[str, Any]:
    completed = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)


def parse_last_json_block(text: str) -> Dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("JSON_RESULT="):
            return json.loads(line.split("=", 1)[1])
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("No trailing JSON block found", text, 0)


def docker_exec_json(container: str, python_code: str) -> Dict[str, Any]:
    cmd = [
        "docker", "exec", "-i", container, "env", "PYTHONPATH=/app:/app/corpus-tools", "python", "-"
    ]
    completed = subprocess.run(cmd, input=python_code, text=True, capture_output=True, check=True)
    return parse_last_json_block(completed.stdout)


def docker_exec_text(container: str, command: str) -> str:
    completed = subprocess.run(["docker", "exec", container, "sh", "-lc", command], capture_output=True, text=True, check=True)
    return completed.stdout


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_selected_docs(corpus_dir: Path, pilot_result: Dict[str, Any], stage_dir: Path) -> Path:
    ensure_clean_dir(stage_dir)
    selected_rows = []
    for doc in pilot_result.get("documents", []):
        rel_json = doc["normalized_json"]
        src_json = corpus_dir / rel_json
        src_md = src_json.with_name("document.md")
        dst_json = stage_dir / rel_json
        dst_md = dst_json.with_name("document.md")
        dst_json.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_json, dst_json)
        if src_md.exists():
            shutil.copy2(src_md, dst_md)
        selected_rows.append({"normalized_json": rel_json, "source_url": doc.get("source_url"), "id": doc.get("id")})
    selected_path = stage_dir / "selected-documents.json"
    selected_path.write_text(json.dumps(selected_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return selected_path


def main() -> int:
    args = parse_args()
    tools_root = Path(__file__).resolve().parent.parent
    state_file = Path(args.state_file)
    runs_dir = Path(args.runs_dir)
    corpus_root = Path(args.corpus_root)
    staging_root = Path(args.staging_root)
    runs_dir.mkdir(parents=True, exist_ok=True)
    corpus_root.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)

    species_order = [s.strip() for s in args.species_order.split(",") if s.strip()]
    state = load_state(state_file, species_order)
    species = state["species_order"][state["next_species_index"]]
    page = int(state["pages"].get(species, 1))
    ts = utc_now()

    corpus_dir = corpus_root / f"live-native-{species_slug(species)}"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    pilot_cmd = [
        sys.executable,
        str(Path(__file__).resolve().with_name("pilot_export_infohub_native.py")),
        "--species", species,
        "--page", str(page),
        "--page-size", str(args.page_size),
        "--count", str(args.count),
        "--output-dir", str(corpus_dir),
    ]
    pilot_result = run_json(pilot_cmd, cwd=tools_root)

    exported_count = int(pilot_result.get("count_exported", 0))
    stage_dir = staging_root / f"{ts}-{species_slug(species)}-page-{page:04d}"
    selected_json = copy_selected_docs(corpus_dir, pilot_result, stage_dir)
    container_stage_dir = Path("/app/corpus-sync-stage/current") / stage_dir.name

    # Refresh tools + stage corpus in container
    docker_exec_text(args.container, "rm -rf /app/corpus-sync-stage/current && mkdir -p /app/corpus-sync-stage/current /app/corpus-tools /app/corpus-tools/export_pipeline /app/corpus-tools/scripts")
    subprocess.run(["docker", "cp", str(tools_root / "export_pipeline/."), f"{args.container}:/app/corpus-tools/export_pipeline/"], check=True)
    subprocess.run(["docker", "cp", str(tools_root / "scripts/."), f"{args.container}:/app/corpus-tools/scripts/"], check=True)
    subprocess.run(["docker", "cp", str(stage_dir / "."), f"{args.container}:/app/corpus-sync-stage/current/"], check=True)

    before_counts = docker_exec_json(
        args.container,
        """
import json
from sqlalchemy import text
from core.database import engine
with engine.connect() as conn:
    docs = conn.execute(text(\"SELECT COUNT(*) FROM documents\")).scalar()
    chunks = conn.execute(text(\"SELECT COUNT(*) FROM document_chunks\")).scalar()
    emb = conn.execute(text(\"SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL\")).scalar()
    print(\"JSON_RESULT=\" + json.dumps({\"documents\": docs, \"chunks\": chunks, \"embedded_chunks\": emb}))
""",
    )

    index_result = docker_exec_json(
        args.container,
        f"""
import json
from pathlib import Path
from export_pipeline.corpus_indexer import CorpusIndexer
indexer = CorpusIndexer(Path('{container_stage_dir.as_posix()}'))
stats = indexer.index_corpus(
  selected_json=Path('{(container_stage_dir / 'selected-documents.json').as_posix()}'),
  write_db=True,
  embed=True,
)
print(\"JSON_RESULT=\" + json.dumps(stats.__dict__))
""",
    )

    after_counts = docker_exec_json(
        args.container,
        """
import json
from sqlalchemy import text
from core.database import engine
with engine.connect() as conn:
    docs = conn.execute(text(\"SELECT COUNT(*) FROM documents\")).scalar()
    chunks = conn.execute(text(\"SELECT COUNT(*) FROM document_chunks\")).scalar()
    emb = conn.execute(text(\"SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL\")).scalar()
    print(\"JSON_RESULT=\" + json.dumps({\"documents\": docs, \"chunks\": chunks, \"embedded_chunks\": emb}))
""",
    )

    # Advance state: alternate species every tick; pages increment per-species.
    next_state = state
    next_state["pages"][species] = 1 if exported_count == 0 else page + 1
    next_state["next_species_index"] = (state["next_species_index"] + 1) % len(state["species_order"])
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run_result = SyncRunResult(
        ts=ts,
        species=species,
        page=page,
        page_size=args.page_size,
        exported_count=exported_count,
        corpus_dir=str(corpus_dir),
        stage_dir=str(stage_dir),
        before_counts=before_counts,
        after_counts=after_counts,
        pilot_result=pilot_result,
        index_result=index_result,
        next_state=next_state,
    )
    run_path = runs_dir / f"{ts}-{species_slug(species)}-page-{page:04d}.json"
    run_path.write_text(json.dumps(asdict(run_result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(asdict(run_result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
