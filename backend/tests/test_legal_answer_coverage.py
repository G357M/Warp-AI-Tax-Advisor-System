from scripts.audit_legal_answer_coverage import (
    PARSER_SOURCE_PATH,
    PUBLIC_RESPONSE_SOURCE_PATH,
    audit_coverage,
    extract_hardcoded_fact_topics,
    extract_parser_goals,
)


def test_all_parser_goals_have_an_explicit_answer_or_retrieval_policy():
    report = audit_coverage()

    assert report["result"] == "pass"
    assert report["parser_goal_count"] == 11
    assert report["contract_backed_goal_count"] == 7
    assert report["contextual_retrieval_goal_count"] == 4
    assert report["classified_goal_coverage"] == 1.0
    assert report["uncovered_goals"] == []
    assert report["legacy_hardcoded_fact_topics"] == ["funded_pension"]
    assert report["error_count"] == 0
    assert report["network_calls_allowed"] is False
    assert report["database_calls_allowed"] is False
    assert report["llm_calls_allowed"] is False


def test_parser_goal_extractor_detects_new_unclassified_goal():
    source = PARSER_SOURCE_PATH.read_text(encoding="utf-8") + "\ngoal = 'new_unclassified_goal'\n"

    report = audit_coverage(parser_source=source)

    assert report["result"] == "fail"
    assert report["uncovered_goals"] == ["new_unclassified_goal"]
    assert "uncovered parser goal: new_unclassified_goal" in report["errors"]


def test_legacy_fact_extractor_rejects_an_unreviewed_hardcoded_answer():
    source = PUBLIC_RESPONSE_SOURCE_PATH.read_text(encoding="utf-8")
    source = source.replace(
        "    return None\n\n\ndef small_business_legal_form_response",
        "    return 'unreviewed_fact', pick({'ru': 'x'})\n\n\ndef small_business_legal_form_response",
        1,
    )

    assert "unreviewed_fact" in extract_hardcoded_fact_topics(source)
    report = audit_coverage(public_response_source=source)
    assert report["result"] == "fail"
    assert "unexpected hard-coded authoritative fact: unreviewed_fact" in report["errors"]


def test_legacy_fact_extractor_rejects_a_direct_literal_answer():
    source = PUBLIC_RESPONSE_SOURCE_PATH.read_text(encoding="utf-8")
    source = source.replace(
        "    return None\n\n\ndef small_business_legal_form_response",
        "    if 'literal' in q:\n"
        "        return 'literal_fact', 'unreviewed legal answer'\n\n"
        "    return None\n\n\ndef small_business_legal_form_response",
        1,
    )

    assert "literal_fact" in extract_hardcoded_fact_topics(source)
    report = audit_coverage(public_response_source=source)
    assert "unexpected hard-coded authoritative fact: literal_fact" in report["errors"]


def test_extractors_are_derived_from_source_syntax_not_manual_goal_lists():
    parser_goals = extract_parser_goals(PARSER_SOURCE_PATH.read_text(encoding="utf-8"))
    hardcoded_topics = extract_hardcoded_fact_topics(
        PUBLIC_RESPONSE_SOURCE_PATH.read_text(encoding="utf-8")
    )

    assert "profit_distribution_model" in parser_goals
    assert hardcoded_topics == {"funded_pension"}
