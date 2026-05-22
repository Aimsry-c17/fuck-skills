# Dynamic Skill Router v2 design

## Goal

Upgrade the router from "one request -> one skill" to "one request -> multiple ordered parts -> best skill per part".

## Main workflow

1. Decompose the user request into ordered capability parts.
2. For each part, decide whether an external skill is needed.
3. For each skill-worthy part, generate 1-3 focused queries.
4. Search `skills.sh` for each query.
5. Merge and deduplicate candidates per part.
6. Filter for relevance.
7. Among relevant candidates, choose the highest-install skill.
8. Reuse already selected skills across later parts when reasonable.
9. Execute parts in order.
10. Clean up all temporary skills at the end.

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

Example:

- part 1: review the PR
- part 2: add test coverage
- part 3: write changelog

## TaskPart

```json
{
  "part_id": "part-1",
  "title": "Review the pull request",
  "capability": "review",
  "priority": 1,
  "needs_skill": true,
  "status": "pending"
}
```

## Query generation

Generate 1-3 queries per skill-worthy part.

Preferred query patterns:

- `<domain> <task>`
- `<tool> <task>`
- `<capability> best practices`
- `<framework> workflow`

Examples:

- `pr review`
- `react testing`
- `jest testing`
- `release notes`
- `vercel deploy`

## SkillCandidate

```json
{
  "package": "owner/repo@skill-name",
  "repo": "owner/repo",
  "skill": "skill-name",
  "installs_text": "42.6K",
  "installs_value": 42600,
  "url": "https://skills.sh/owner/repo/skill-name",
  "matched_queries": ["pr review", "code review"],
  "relevance": "high"
}
```

## Ranking rule

Use a two-stage decision rule.

### Stage 1: relevance filtering

Drop candidates that are clearly misaligned with the part.

### Stage 2: popularity sorting

Among the remaining candidates, sort by install count descending and take top 1.

This means:

- not "the hottest skill on the site"
- but "the hottest relevant skill for this part"

## SkillSelection

```json
{
  "part_id": "part-1",
  "selected_skill": "owner/repo@skill-name",
  "selection_reason": "Highest-install relevant skill for PR review",
  "reused_from_part_id": null
}
```

## Reuse rule

Reuse an already selected skill when:

- it already covers the current part well
- reuse does not noticeably reduce quality
- the new part does not require a clearly more specialized skill

Avoid repeated installation of overlapping skills.

## Execution model

Execute parts in order.

For each part:

1. resolve the selected or reusable skill
2. install it if needed
3. read its `SKILL.md`
4. read only the references needed for the current part
5. run only the relevant scripts
6. complete the part
7. record what happened

## ExecutionRecord

```json
{
  "part_id": "part-1",
  "skill": "owner/repo@skill-name",
  "installed_now": true,
  "installed_path": "/path/to/skill",
  "result_summary": "PR review completed",
  "cleanup_needed": true
}
```

## Cleanup policy

Prefer unified cleanup after the entire request completes.

Remove only skills that:

- were installed specifically for the current task
- are no longer needed by later parts
- are not explicitly requested to remain installed

Keep skills that:

- existed before the task
- will be reused by later parts
- are explicitly requested to remain installed

## Fallback rules

If a part has no strong relevant candidates:

- mark it for fallback
- solve it directly without an external skill

If installation fails:

- explain the failure
- try the next relevant candidate when reasonable
- otherwise fall back to direct execution

If a selected skill is too weak or vague:

- try top 2
- otherwise fall back

## Recommended implementation phases

### Phase 1

Update `SKILL.md` to reflect part-based routing.

### Phase 2

Extend the helper script with:

- multi-query aggregation
- install count parsing
- candidate deduplication
- ranking helpers

### Phase 3

Add a decomposition layer that outputs ordered parts.

### Phase 4

Add reuse planning and unified cleanup.

### Phase 5

Add safety thresholds and fallback tuning.
