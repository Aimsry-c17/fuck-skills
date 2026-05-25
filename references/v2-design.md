# fuck-skills v2 design

## Goal

Upgrade the router from "one request -> one skill" to "one request -> multiple ordered parts -> best skill per part".

## Non-goals

This version does not require:

- platform-native hot-loading of newly installed skills
- parallel execution of multiple skills
- ML-based reranking
- persistent cross-session caching

## Part model

A request should be decomposed into capability parts, not grammar fragments.

Preferred capabilities include:

- review
- testing
- deployment
- documentation
- refactor
- analysis
- migration
- integration

### TaskPart

```json
{
  "part_id": "part-1",
  "title": "Review the pull request",
  "capability": "review",
  "needs_skill": true,
  "queries": ["pr review", "code review"]
}
```

## Query generation

Generate 1-3 queries per skill-worthy part.

Preferred query patterns:

- `<domain> <task>`
- `<tool> <task>`
- `<capability> best practices`
- `<framework> workflow`

## SkillCandidate

Returned by `search_query` / `merge_candidates`:

```json
{
  "package": "owner/repo@skill-name",
  "repo": "owner/repo",
  "skill": "skill-name",
  "installs_text": "42.6K",
  "installs_value": 42600,
  "url": "https://skills.sh/owner/repo/skill-name",
  "matched_queries": ["pr review", "code review"]
}
```

After scoring by `score_candidate`, additional fields:

```json
{
  "relevance_score": 85,
  "relevance": "high",
  "overlap_tokens": ["review", "code"],
  "exact_query_matches": ["pr review"],
  "score_breakdown": {
    "token_overlap": 20,
    "token_count": 2,
    "overlap_tokens": ["review", "code"],
    "exact_query_match": 60,
    "exact_matches": ["pr review"],
    "capability_match": 0,
    "title_match": 0,
    "skill_name_match": 0,
    "total": 80
  }
}
```

## Ranking rule

Candidates are sorted by `(relevance_score, installs_value)` descending — relevance first, then popularity within relevant candidates. This means "highest-install relevant skill for this part", not "globally hottest skill".

Relevance thresholds (configurable via `--relevance-high` / `--relevance-medium`):

- score >= 80 → high
- score >= 30 → medium
- score > 0 → low
- score == 0 → none (filtered out)

## SkillSelection (per-part output from batch-select)

```json
{
  "part_id": "part-1",
  "title": "Review the pull request",
  "capability": "review",
  "needs_skill": true,
  "selected": { "<SkillCandidate>" },
  "reused": false,
  "reused_from_package": null,
  "selection_reason": "Highest-install relevant skill for this part",
  "fallback": false,
  "candidates": ["<filtered candidates>"],
  "all_candidates": ["<all ranked candidates>"]
}
```

Batch output may also include a `summary` object with `packages_to_install`, `already_installed_packages`, `fallback_parts`, and `reused_parts` to support dry-run preview.

## Reuse rule

`reuse_or_select` tracks previously selected skills in a registry. For each new part, before choosing a new skill, it scores all previously selected skills against the new part. A previously selected skill is reused only when it scores at least as high as the best new candidate, reaches at least medium relevance, and still shows a strong signal for the new part (for example exact query or capability alignment).

## Execution model

Execute parts in order. For each part:

1. resolve the selected or reusable skill
2. install it if not already installed
3. read its `SKILL.md`
4. read only the references needed for the current part
5. run only the relevant scripts
6. complete the part

## Cleanup policy

Unified cleanup after the entire request completes. Remove only skills that were installed specifically for the current task and were not already installed before the session. Prefer removing by full package reference when possible. Cleanup should rely on the `skills remove` command rather than manually deleting skill directories from this router.
