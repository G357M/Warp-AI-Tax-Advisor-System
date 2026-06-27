# RAG v2 canonical-law rollout performance note (2026-05-08)

## Scope

This note summarizes observed production behavior for `canonical_law_lookup` on the live public query route after enabling rollout for:

- `named_document_lookup`
- `canonical_law_lookup`

The observations below come from repeated live checks against `/api/v1/public/query` on production.

## Correctness summary

With safe pacing below the guest public rate limit, the sampled canonical-law queries were stable:

- 12 representative canonical-law queries
- 4 repeats each
- 48/48 successful responses
- 0 weak answers
- 0 rate-limited responses
- 0 transport errors

This strongly suggests the earlier apparent instability was caused by public endpoint burst rate limiting rather than canonical-law retrieval logic.

## Observed latency bands

### Fast cases (~1.8s-3.0s)

Typical examples:
- short article queries such as article 166
- short point/part queries such as 166.1, 168.1, 169.1, 169 part 1

Observed band:
- roughly `1.8s-3.0s`

### Medium cases (~6s-8s)

Typical examples:
- article 168
- article 169
- article 170

Observed band:
- roughly `6s-8s`

### Heavy cases (~8.7s-19.5s)

Typical examples:
- article 172
- short-form `ст. 172 п. 1`
- article 170 point 1
- `ст. 170 ч. 1`

Observed band:
- roughly `8.7s-19.5s`
- worst observed cases in this sample were around article 170 point/part requests

## Likely hotspots

The main cost does not currently look like routing instability. The likely hotspots are:

1. **Large section extraction from `Document.full_text`**
   - heavier articles require scanning and slicing larger document regions
   - point/part requests on long sections appear to amplify this cost

2. **Longer LLM generation on dense legal sections**
   - broader article text produces longer context and longer summaries
   - the slowest cases correlate with content-heavy sections, not with lookup misses

3. **Public-route operational limits can distort naive benchmarks**
   - guest public rate limit is still `10/minute`
   - burst tests against the public endpoint can create false “weak answer” signals unless `429` is classified separately

## Practical guidance

For correctness watches on the public endpoint:
- use paced checks
- treat `429` separately from retrieval/model weakness
- prefer the dedicated stability-watch helper script

For future performance work, the best next low-risk targets are:

1. reduce the amount of extracted section text sent to generation for long article/point cases
2. tighten section boundaries for long canonical-law articles
3. measure whether article 170 / 172 can be shortened before LLM generation without hurting answer quality

## Operational conclusion

As of 2026-05-08, `canonical_law_lookup` appears production-stable on the sampled public-route queries.
The main remaining concern is performance variance on heavier article/point requests, not answer correctness.


## Update: heavy point/part optimization validated

A later focused performance pass confirmed that the main heavy-case bottleneck was LLM generation over long point-based legal contexts rather than retrieval.

### Measured before optimization
- `статья 168 пункт 1` -> context ~275 chars, generation ~2.1s
- `статья 170 пункт 1` -> context ~3908 chars, generation ~9.1s

### Minimal optimization applied
For long point-based rollout contexts (over ~2500 chars), the rollout runtime now keeps the same retrieved source context but asks the generator to answer briefly (2-4 sentences, only key rules/categories, no long rewrite of every subpoint).

### Result on live heavy subset
Using paced public-route checks after deployment:
- `статья 170 пункт 1` -> ~2.62s average
- `ст. 170 ч. 1` -> ~2.00s average
- `ст. 172 п. 1` -> ~2.98s average
- 6/6 successful
- 0 weak answers
- 0 rate-limited
- 0 transport errors

### Interpretation
This was a material latency improvement without changing the public API contract or the rollout eligibility logic. The remaining performance question is now mainly about long article-level canonical-law summaries rather than point/part cases.
