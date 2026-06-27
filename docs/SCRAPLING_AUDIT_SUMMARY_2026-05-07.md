# Scrapling Audit Summary — 2026-05-07

## Scope

This report summarizes the targeted live evaluation of Scrapling inside the real `tax-advisor.ge` / `/root/infohub` production project.

Goal: determine whether Scrapling should become a preferred extractor for any meaningful segment of the current corpus, or remain limited to audit / fallback / repair usage.

## Evaluated segments

### 1) Long multi-page normative documents
Primary target because this was the highest-value and highest-risk segment.

Evaluated buckets:
- long `law`
- long `regulation`

Artifacts:
- `state/scrapling-long-law-audit/long_law_regulation_audit_20260507_171017.json`
- `state/scrapling-long-law-audit/long_law_regulation_audit_20260507_171017.csv`
- `state/scrapling-long-law-audit/long_law_regulation_audit_20260507_171515.json`
- `state/scrapling-long-law-audit/long_law_regulation_audit_20260507_171515.csv`

Key result:
- expanded audit sample: `100 law + 100 regulation = 200 documents`
- `used_scrapling_count = 0`
- current native `description -> exporter` path consistently matched or outperformed Scrapling
- Scrapling was usually shorter than baseline, especially on table-heavy and appendix-heavy regulations
- tail overlap between current normalized output and repaired output remained very high (`~0.98` average), indicating the current pipeline already preserves document tails well

Conclusion:
- Scrapling should **not** be enabled as preferred extractor for long `law` / `regulation`

## 2) Short / card-like `news`

Reason for selection:
- many short `news` items have small DB text and 1-2 chunks, so this looked like a plausible segment where Scrapling might recover hidden body text

Artifacts:
- `state/scrapling-news-card-audit/news_card_audit_20260507_173419.json`
- `state/scrapling-news-card-audit/news_card_audit_20260507_173419.csv`

Pilot result:
- sample size: `60`
- `used_scrapling_count = 0`
- average baseline body and Scrapling text were close, but Scrapling did not materially exceed baseline
- current normalized output was often longer because the existing exporter adds useful metadata/context wrapper around otherwise short legislative/news cards

Conclusion:
- for short/card-like `news`, Scrapling does **not** provide meaningful extraction advantage
- current output quality here comes mainly from structured metadata wrapping, not from HTML recovery

## 3) Metadata-heavy anomaly pattern

Reason for selection:
- identify documents where normalized output looked much larger than extracted body, to test whether the system was masking hidden extraction loss

Artifacts:
- `state/scrapling-anomaly-audit/metadata_heavy_anomaly_audit_20260507_*.json`
- `state/scrapling-anomaly-audit/metadata_heavy_anomaly_audit_20260507_*.csv`

Result:
- dominant pattern was not “lost body text”
- dominant pattern was short legislative amendments / short cards where the body itself is naturally small
- current normalized output is longer mostly because it includes useful metadata/title wrapper
- Scrapling did not recover missing primary text in a meaningful way

Conclusion:
- this anomaly class is mostly benign and expected
- it is not evidence that the main extractor is losing document body that Scrapling can restore

## 4) True outlier / control-shot audit

Reason for selection:
- final stress test for the strongest possible Scrapling win cases
- targeted documents with:
  - `chunk_count <= 1`
  - very short DB text
  - strong wrapper-vs-body mismatch expectations

Artifacts:
- `state/scrapling-true-outlier-audit/true_outlier_audit_20260507_181734.json`
- `state/scrapling-true-outlier-audit/true_outlier_audit_20260507_181734.csv`

Result:
- raw candidates inspected: `250`
- filtered true outliers: `0`
- `used_scrapling_count = 0`

Conclusion:
- even in the hardest candidate pool, Scrapling did not surface meaningful hidden body recovery cases

## Overall conclusion

Across all tested segments, Scrapling did **not** demonstrate enough value to justify rollout as a preferred extractor for the current `tax-advisor.ge` corpus.

This includes:
- high-value long normative material
- short/card-like news
- metadata-heavy anomaly patterns
- extreme short-document outliers

## Operational decision

For the current live project, Scrapling should remain:
- an **audit/debug tool**
- a **fallback utility**
- a **repair utility**

Scrapling should **not** be treated as:
- the main ingestion backbone
- the default extractor for `law`
- the default extractor for `regulation`
- the default extractor for `news`
- the default extractor for short anomaly/outlier segments

## Practical interpretation

The current production extraction path is already correctly centered on native InfoHub payloads, especially `native_detail.description` and the existing export/normalization logic.

The most important confirmed lesson is:
- the earlier major failures were primarily DB/index/chunk representation problems, not broad source-body extraction failures

That means further quality work should focus on:
- retrieval/ranking quality
- corpus routing / normative-vs-dispute selection
- selective repair when explicit anomalies appear

—not on replacing the current extractor with Scrapling.

## Status decision for future work

Default position going forward:
- keep current native extraction path as primary
- keep Scrapling code in repository for diagnostics/fallback/repair
- do not spend more time searching for rollout segments unless a new concrete failure pattern appears in production
