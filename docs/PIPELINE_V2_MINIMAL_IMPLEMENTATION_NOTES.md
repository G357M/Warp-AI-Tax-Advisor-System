# Pipeline V2 minimal implementation notes

This note captures the minimal no-big-refactor implementation that was added on top of `backend/rag_v2`.

## 1. Candidate / chunk metadata fields

Added or normalized in candidate metadata:

- `source_class`
- `title_normalized`
- `retrieval_origin`
- `retrieval_scores`
- `retrieval_channels`
- `authority_rank`
- `applicability_topics`
- `applicability_subjects`
- `applicability_goals`
- `matched_doc_number`
- `matched_article_ref`
- `matched_point_ref`
- `chunk_metadata_version`
- `is_current`
- `recency_bucket`
- `localities`

These fields are enough for routing-aware rerank and source audit without changing the full storage model.

## 2. Score formula

Current rerank score is the weighted sum of:

- `class_fit`
- `authority`
- `subject_match`
- `goal_match`
- `specificity`
- `exactness`
- `lexical_support`
- `semantic_support`
- `metadata_support`
- `freshness`
- `merge_bonus`

High-level formula:

```text
final_score =
  class_fit * W_class_fit +
  authority * W_authority +
  subject_match * W_subject_match +
  goal_match * W_goal_match +
  specificity * W_specificity +
  exactness * W_exactness +
  lexical_support * W_lexical_support +
  semantic_support * W_semantic_support +
  metadata_support * W_metadata_support +
  freshness * W_freshness +
  merge_bonus * W_merge_bonus
```

Weights vary by question class in `rerank_policy.py`.

## 3. Routing pseudocode

```python
parsed = parse_query(query)
classification = classify_query(parsed)
routing_profile = routing_profile_for(classification.question_class, parsed)

candidate_map = {}
for channel in channels_sorted_by_priority(routing_profile):
    items = channel.fetch(parsed)
    items = enrich_metadata(items, channel)
    candidate_map[channel.name] = items

    if routing_profile.stop_on_exact and channel.name in {"exact_doc_resolver", "citation_resolver"} and items:
        break

merged = merge_candidates(candidate_map)
ranked = rerank_candidates(parsed, classification, merged)
audit = audit_sources(parsed, classification, ranked)
context = build_context_plan(ranked, classification.question_class)
```

## 4. Minimal rollout order

Recommended order without big refactor:

1. named document lookup
2. article / point lookup
3. practical guidance
4. dispute practice
5. local regulation lookup
6. amendment tracking

## 5. Regression coverage added

Added `tests/test_rag_v2_pipeline.py` covering:

- practical guidance
- named document direct resolution
- article lookup
- dispute decision lookup
- local regulation lookup
- amendment tracking
