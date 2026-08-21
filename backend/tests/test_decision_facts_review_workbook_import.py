"""Security and conversion contracts for expert-review XLSX imports."""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from xml.sax.saxutils import escape

import pytest

from scripts import build_decision_facts_full_review_bundle as bundle_builder
from scripts import import_decision_facts_review_workbook as importer


def _member(document_id: str) -> dict:
    return {
        "facts_id": f"facts-{document_id}",
        "document_id": document_id,
        "title": f"Decision {document_id}",
        "source_url": f"https://infohub.rs.ge/ka/workspace/document/{document_id}",
        "document_number": "11623",
        "date_published": "2026-05-27",
        "file_hash": "a" * 64,
        "content_length": 100,
        "content_md5": "b" * 32,
        "normalized_content_md5": "b" * 32,
        "authority_body": "revenue_service_council",
        "dispute_type": "tax",
        "outcome": "satisfied",
        "in_favor": "taxpayer",
        "decision_number": "11623",
        "decision_date": "2026-05-27",
        "case_number": None,
    }


def _bundle() -> dict:
    return {
        "schema_version": 1,
        "bundle_type": "decision_facts_full_expert_review",
        "generated_at_utc": "2026-08-20T00:00:00+00:00",
        "source": {
            "report_sha256": "a" * 64,
            "source_snapshot_sha256": "b" * 64,
            "contract_version": "2026-08-20.1",
            "contract_sha256": "c" * 64,
            "deployed_commit": "abc123",
            "report_generated_at_utc": "2026-08-20T00:00:00+00:00",
        },
        "review_contract": {
            "field_verdicts": [
                "correct",
                "incorrect",
                "not_applicable",
                "unable_to_verify",
            ],
            "duplicate_verdicts": [
                "true_duplicate",
                "distinct_decisions",
                "mixed_group",
                "unable_to_verify",
            ],
            "confidence_values": ["high", "medium", "low"],
            "database_writes_allowed": False,
        },
        "counts": {
            "review_items": 0,
            "duplicate_groups": 1,
            "duplicate_members": 2,
        },
        "review_items": [],
        "duplicate_groups": [
            {
                "group_id": "DFG-TEST",
                "candidate_class": "exact",
                "authority_body": "revenue_service_council",
                "normalized_number": "011623",
                "member_count": 2,
                "signals": {"same_content": True},
                "members": [_member("doc-a"), _member("doc-b")],
                "review": {
                    "review_state": "pending",
                    "duplicate_verdict": "",
                    "canonical_document_id": "",
                    "proposed_exclusions_json": [],
                    "evidence_locator": "",
                    "legal_rationale": "",
                    "confidence": "",
                    "reviewer": "",
                    "reviewed_at_utc": "",
                    "second_reviewer": "",
                    "second_reviewed_at_utc": "",
                    "notes": "",
                },
            }
        ],
    }


def _matrix(bundle: dict) -> list[list[str]]:
    payload = bundle_builder.render_duplicate_groups(bundle).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(payload, newline="")))


def _xlsx_bytes(
    matrix: list[list[str]],
    *,
    sheet_name: str = "duplicate_groups completed",
    formula_cell: str | None = None,
    numeric_cell: str | None = None,
    external_relationship: bool = False,
    absolute_sheet_target: bool = False,
) -> bytes:
    strings: list[str] = []
    string_index: dict[str, int] = {}

    def shared_index(value: str) -> int:
        if value not in string_index:
            string_index[value] = len(strings)
            strings.append(value)
        return string_index[value]

    def column_name(index: int) -> str:
        name = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(ord("A") + remainder) + name
        return name

    cells = []
    for row_index, row in enumerate(matrix, start=1):
        row_cells = []
        for column_index, value in enumerate(row, start=1):
            reference = f"{column_name(column_index)}{row_index}"
            if reference == formula_cell:
                row_cells.append(f'<c r="{reference}" t="str"><f>1+1</f><v>2</v></c>')
            elif reference == numeric_cell:
                row_cells.append(f'<c r="{reference}" t="n"><v>{escape(value)}</v></c>')
            elif value:
                row_cells.append(
                    f'<c r="{reference}" t="s"><v>{shared_index(value)}</v></c>'
                )
        cells.append(f'<row r="{row_index}">{"".join(row_cells)}</row>')

    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""
    workbook = f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    sheet_target = (
        "/xl/worksheets/sheet1.xml"
        if absolute_sheet_target
        else "worksheets/sheet1.xml"
    )
    workbook_rels = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{sheet_target}"/>
 <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""
    sheet = f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <sheetData>{''.join(cells)}</sheetData>
</worksheet>"""
    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(f"<si><t>{escape(value)}</t></si>" for value in strings)
        + "</sst>"
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/sharedStrings.xml", shared)
        if external_relationship:
            archive.writestr(
                "xl/worksheets/_rels/sheet1.xml.rels",
                """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://evil.test" TargetMode="External"/>
</Relationships>""",
            )
    return payload.getvalue()


def _filled_matrix(*, complete: bool = False) -> tuple[dict, list[list[str]]]:
    bundle = _bundle()
    matrix = _matrix(bundle)
    headers = matrix[0]
    row = dict(zip(headers, matrix[1], strict=True))
    row.update(
        {
            "review_state": "complete" if complete else "pending",
            "duplicate_verdict": "true_duplicate",
            "canonical_document_id": "doc-a",
            "proposed_exclusions_json": '[ "doc-b" ]',
            "evidence_locator": "Official InfoHub documents",
            "legal_rationale": "Same official legal act.",
            "confidence": "high",
            "reviewer": "expert-a" if complete else "",
            "reviewed_at_utc": "2026-08-20T12:00:00Z" if complete else "",
            "second_reviewer": "expert-b" if complete else "",
            "second_reviewed_at_utc": "2026-08-20T13:00:00Z" if complete else "",
        }
    )
    return bundle, [headers, [row[field] for field in headers]]


def _review_item_bundle_and_matrix() -> tuple[dict, list[list[str]]]:
    bundle = _bundle()
    item = {
        **_member("fact-doc"),
        "review_id": "DFR-TEST",
        "contested_articles": ["98²"],
        "amount_gel": 100.0,
        "queue_reasons": ["non_simple_article_reference"],
        "review": {
            "review_state": "pending",
            **{field: "" for field in bundle_builder.FIELD_VERIFICATIONS},
            "evidence_locator": "",
            "proposed_corrections_json": {},
            "legal_rationale": "",
            "confidence": "",
            "reviewer": "",
            "reviewed_at_utc": "",
            "second_reviewer": "",
            "second_reviewed_at_utc": "",
            "notes": "",
        },
    }
    bundle["review_items"] = [item]
    bundle["duplicate_groups"] = []
    bundle["counts"] = {
        "review_items": 1,
        "duplicate_groups": 0,
        "duplicate_members": 0,
    }
    payload = bundle_builder.render_review_items(bundle).decode("utf-8-sig")
    matrix = list(csv.reader(io.StringIO(payload, newline="")))
    return bundle, matrix


def test_pending_prefill_is_normalized_without_fabricating_attribution():
    bundle, matrix = _filled_matrix()
    parsed = importer.read_text_worksheet(
        _xlsx_bytes(matrix, absolute_sheet_target=True),
        sheet_name="duplicate_groups completed",
        expected_columns=len(matrix[0]),
    )

    rows, payload, counts = importer.build_import(
        bundle, parsed, review_type="duplicate-groups"
    )

    assert counts == {"rows": 1, "completed": 0, "pending": 1, "prefilled_pending": 1}
    assert rows[0]["proposed_exclusions_json"] == '["doc-b"]'
    assert rows[0]["reviewer"] == ""
    assert payload.startswith(b"\xef\xbb\xbf")


def test_complete_duplicate_requires_and_accepts_distinct_second_review():
    bundle, matrix = _filled_matrix(complete=True)
    parsed = importer.read_text_worksheet(
        _xlsx_bytes(matrix),
        sheet_name="duplicate_groups completed",
        expected_columns=len(matrix[0]),
    )

    _, _, counts = importer.build_import(bundle, parsed, review_type="duplicate-groups")

    assert counts["completed"] == 1
    second_reviewer = matrix[0].index("second_reviewer")
    matrix[1][second_reviewer] = "expert-a"
    parsed = importer.read_text_worksheet(
        _xlsx_bytes(matrix),
        sheet_name="duplicate_groups completed",
        expected_columns=len(matrix[0]),
    )
    with pytest.raises(ValueError, match="second_reviewer must differ"):
        importer.build_import(bundle, parsed, review_type="duplicate-groups")


def test_review_item_worksheet_uses_the_same_immutable_contract():
    bundle, matrix = _review_item_bundle_and_matrix()
    parsed = importer.read_text_worksheet(
        _xlsx_bytes(matrix, sheet_name="review_items completed"),
        sheet_name="review_items completed",
        expected_columns=len(matrix[0]),
    )

    rows, _, counts = importer.build_import(bundle, parsed, review_type="review-items")

    assert counts == {"rows": 1, "completed": 0, "pending": 1, "prefilled_pending": 0}
    assert rows[0]["review_id"] == "DFR-TEST"
    assert rows[0]["proposed_corrections_json"] == "{}"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"formula_cell": "L2"}, "formulas are prohibited"),
        ({"numeric_cell": "D2"}, "must be stored as text"),
        ({"external_relationship": True}, "external XLSX relationships"),
    ],
)
def test_active_or_implicitly_typed_workbook_content_is_rejected(kwargs, message):
    _, matrix = _filled_matrix()

    with pytest.raises(ValueError, match=message):
        importer.read_text_worksheet(
            _xlsx_bytes(matrix, **kwargs),
            sheet_name="duplicate_groups completed",
            expected_columns=len(matrix[0]),
        )


def test_immutable_column_change_and_invalid_json_are_rejected():
    bundle, matrix = _filled_matrix()
    normalized_number = matrix[0].index("normalized_number")
    matrix[1][normalized_number] = "11623"
    parsed = importer.read_text_worksheet(
        _xlsx_bytes(matrix),
        sheet_name="duplicate_groups completed",
        expected_columns=len(matrix[0]),
    )
    with pytest.raises(ValueError, match="immutable field changed"):
        importer.build_import(bundle, parsed, review_type="duplicate-groups")

    bundle, matrix = _filled_matrix()
    exclusions = matrix[0].index("proposed_exclusions_json")
    matrix[1][exclusions] = "[doc-b]"
    parsed = importer.read_text_worksheet(
        _xlsx_bytes(matrix),
        sheet_name="duplicate_groups completed",
        expected_columns=len(matrix[0]),
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        importer.build_import(bundle, parsed, review_type="duplicate-groups")


def test_csv_formula_prefixes_are_neutralized():
    bundle, matrix = _filled_matrix()
    rationale = matrix[0].index("legal_rationale")
    matrix[1][rationale] = "=dangerous-spreadsheet-formula"
    parsed = importer.read_text_worksheet(
        _xlsx_bytes(matrix),
        sheet_name="duplicate_groups completed",
        expected_columns=len(matrix[0]),
    )

    _, payload, _ = importer.build_import(
        bundle, parsed, review_type="duplicate-groups"
    )
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline="")))

    assert rows[0]["legal_rationale"] == "'=dangerous-spreadsheet-formula"


def test_cli_requires_pinned_hashes_and_writes_exclusively(
    tmp_path, monkeypatch, capsys
):
    bundle, matrix = _filled_matrix()
    bundle_path = tmp_path / "review_bundle.json"
    workbook_path = tmp_path / "duplicate_groups.working.xlsx"
    output_path = tmp_path / "duplicate_groups.imported.csv"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    workbook_path.write_bytes(_xlsx_bytes(matrix))
    os.chmod(bundle_path, 0o600)
    os.chmod(workbook_path, 0o600)

    monkeypatch.setattr(
        "sys.argv",
        [
            "import_decision_facts_review_workbook.py",
            "--bundle",
            str(bundle_path),
            "--workbook",
            str(workbook_path),
            "--review-type",
            "duplicate-groups",
        ],
    )
    assert importer.main() == 0
    plan_line = capsys.readouterr().out.strip()
    plan = json.loads(plan_line.split("=", 1)[1])

    monkeypatch.setattr(
        "sys.argv",
        [
            "import_decision_facts_review_workbook.py",
            "--bundle",
            str(bundle_path),
            "--workbook",
            str(workbook_path),
            "--review-type",
            "duplicate-groups",
            "--execute",
            "--output",
            str(output_path),
            "--expected-bundle-sha256",
            plan["bundle_sha256"],
            "--expected-workbook-sha256",
            plan["workbook_sha256"],
            "--expected-output-sha256",
            plan["output_sha256"],
            "--expected-rows",
            str(plan["rows"]),
        ],
    )
    assert importer.main() == 0
    assert output_path.is_file()
    if os.name == "posix":
        assert (output_path.stat().st_mode & 0o777) == 0o600
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        importer.main()
