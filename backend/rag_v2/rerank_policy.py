from __future__ import annotations

from typing import Dict


def score_weights(question_class: str) -> Dict[str, float]:
    defaults = {
        "class_fit": 1.0,
        "authority": 1.0,
        "subject_match": 1.0,
        "goal_match": 1.0,
        "specificity": 1.0,
        "exactness": 1.0,
        "lexical_support": 1.0,
        "semantic_support": 1.0,
        "metadata_support": 1.0,
        "freshness": 1.0,
        "merge_bonus": 1.0,
    }

    policies = {
        "canonical_law_lookup": {
            **defaults,
            "authority": 1.25,
            "exactness": 1.2,
            "specificity": 0.7,
            "semantic_support": 0.8,
            "lexical_support": 1.1,
            "merge_bonus": 0.4,
        },
        "practical_tax_guidance": {
            **defaults,
            "class_fit": 1.15,
            "goal_match": 1.15,
            "specificity": 1.3,
            "metadata_support": 1.15,
            "semantic_support": 1.05,
            "merge_bonus": 0.35,
        },
        "local_regulation_lookup": {
            **defaults,
            "class_fit": 1.1,
            "authority": 1.1,
            "specificity": 0.9,
            "lexical_support": 1.1,
            "merge_bonus": 0.5,
        },
        "dispute_practice": {
            **defaults,
            "class_fit": 1.2,
            "goal_match": 1.2,
            "specificity": 0.8,
            "semantic_support": 1.15,
            "merge_bonus": 0.2,
        },
        "named_document_lookup": {
            **defaults,
            "exactness": 1.4,
            "specificity": 0.6,
            "lexical_support": 1.1,
            "merge_bonus": 0.1,
        },
        "amendment_tracking": {
            **defaults,
            "authority": 1.2,
            "exactness": 1.15,
            "specificity": 0.8,
            "freshness": 1.2,
            "merge_bonus": 0.4,
        },
    }

    return policies.get(question_class, defaults)
