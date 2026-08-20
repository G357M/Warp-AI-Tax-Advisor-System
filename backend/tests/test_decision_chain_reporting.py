"""Privacy boundary for appeal-chain operational reporting."""

from scripts.link_decision_chains import emit_report


def test_summary_only_omits_document_metadata(capsys):
    facts = [
        {
            "id": "higher-id",
            "body": "mof_dispute_council",
            "number": "private-higher-number",
            "date": "2026-08-20",
            "title": "private higher title",
        },
        {
            "id": "lower-id",
            "body": "revenue_service_council",
            "number": "private-lower-number",
            "date": "2026-08-19",
            "title": "private lower title",
        },
    ]
    edges = {("higher-id", "lower-id"): ("prior_ref", 0.95)}

    emit_report(facts, edges, 0, summary_only=True)

    output = capsys.readouterr().out
    assert "Facts considered: 2" in output
    assert "Links found: 1" in output
    assert "method prior_ref: 1" in output
    assert "private" not in output
    assert "Sample linked pairs" not in output
