---
name: fuck-skills
description: Analyze a user request, decompose it into ordered capability parts, decide which parts need external skills, search skills.sh for each such part, choose the highest-install relevant skill, temporarily install it for Codex, follow the installed skill's instructions to complete the part, reuse skills when possible, and remove temporary skills after the task. Use when a request spans multiple specialized areas such as review, testing, deployment, migration, documentation, or integration and a small on-demand skill set is preferable to keeping many skills installed permanently.
---

# fuck-skills

Use this skill when a single user request may require multiple specialized skills and you want to borrow those skills temporarily instead of keeping a large permanent skill set.

**`<skill_dir>`** in all commands below means the directory containing this SKILL.md file.

## When NOT to use this skill

Skip this skill entirely when the request is:

- a single straightforward task (typo fix, simple explanation, basic refactor)
- completable with built-in tools alone
- too trivial for any community skill to add meaningful value

For a single-part request that DOES need an external skill, use the fast path: `search` → `install` → use → `remove`. Skip the full batch workflow.

## Prerequisites

Verify the runtime environment:

```bash
python3 <skill_dir>/scripts/skills_router.py check --json
```

If any check fails, the output includes a `help` field with installation guidance.

### Required permissions

```json
{
  "permissions": {
    "allow": [
      "Bash(npm *)",
      "Bash(python3 *)"
    ]
  }
}
```

Without these, every `skills` search and install call triggers a permission prompt, defeating the automation purpose.

## Core idea

1. split the request into ordered capability parts
2. decide which parts actually need an external skill
3. search `skills.sh` for each skill-worthy part
4. select the highest-install relevant skill for each part
5. reuse skills across parts when they already cover the new part well
6. clean up temporary skills after the full task is complete

## Workflow

### 0. Preview the plan (always do this first)

Before installing anything, decompose the request and run a dry-run to show the user what will happen:

**Step 0a — Decompose and build the parts JSON.** Each part needs these fields:

| Field | Required | Description |
|-------|----------|-------------|
| `part_id` | yes | unique id, e.g. `"p1"`, `"p2"` |
| `title` | yes | short description, e.g. `"Review PR for security"` |
| `capability` | no | category: `review`, `testing`, `deployment`, `documentation`, `refactor`, `analysis`, `migration`, `integration` |
| `queries` | yes | 1-3 search terms for skills.sh, e.g. `["pr review", "security review"]` |
| `needs_skill` | yes | `true` if an external skill is justified, `false` otherwise |

**Step 0b — Run batch-select with --dry-run:**

```bash
python3 <skill_dir>/scripts/skills_router.py batch-select \
  --parts-json '[{"part_id":"p1","title":"Review PR for security","capability":"review","queries":["pr review","security review"],"needs_skill":true},{"part_id":"p2","title":"Add test coverage","capability":"testing","queries":["test coverage","unit testing"],"needs_skill":true},{"part_id":"p3","title":"Generate changelog","capability":"documentation","queries":["changelog","release notes"],"needs_skill":true}]' \
  --dry-run --json
```

**Step 0c — Present the plan to the user:**
- each part: title, selected skill (package + install count + relevance score), whether reused
- the `summary.packages_to_install` list for newly installed skills
- the `summary.already_installed_packages` list for skills that are already present
- any fallback parts from `summary.fallback_parts`

**Step 0d — Wait for user confirmation before proceeding.**

### 1. Decompose the request into ordered parts

Break the request by capability, not by sentence. Prefer capabilities like: review, testing, deployment, documentation, refactor, analysis, migration, integration.

Good: part 1: review PR → part 2: add tests → part 3: write changelog
Bad: splitting every sentence or grammar fragment

Preserve execution order when the request implies a sequence (review → change → test → document).

### 2. Decide which parts need an external skill

Set `needs_skill=true` when the part is specialized enough that a community skill provides meaningful leverage and no built-in or local skill is a good fit.

Set `needs_skill=false` for: small text edits, simple refactors, basic explanations, trivial formatting.

**Prefer:** framework-specific best practices, PR review workflows, testing playbooks, deployment guides, changelog/release-note generators, migration procedures.

**Avoid:** huge umbrella repos when a focused skill exists, vague low-signal matches, skills implying risky production actions without review, skills duplicating common knowledge, overlapping skills when one covers multiple adjacent parts.

### 3. Generate queries for each skill-worthy part

Create 1-3 focused queries per part. Patterns: `<domain> <task>`, `<tool> <task>`, `<capability> best practices`, `<framework> workflow`.

Examples: `pr review`, `react testing`, `jest testing`, `release notes`, `vercel deploy`.

### 4. Search and select

Run `batch-select` as shown in Step 0b. The script: searches skills.sh for each part's queries, merges/deduplicates candidates, scores by relevance, selects the best skill per part, and detects reuse opportunities — all at once.

For debugging a single part, use `select`:

```bash
python3 <skill_dir>/scripts/skills_router.py select \
  --part-title "Review PR" --capability "review" \
  --query "pr review" --query "code review" --json
```

#### Selection rule

Candidates are sorted by `(relevance_score, installs_value)` descending — **relevance first, then popularity**. This is "hottest RELEVANT skill for this part", not "hottest skill overall".

The `score_breakdown` in the output shows exactly how each candidate was scored (token overlap, exact query match, capability match, title match). Use this to explain selections to the user.

If top candidates have similar scores but imply different approaches, ask the user to choose.

### 5. Reuse skills when possible

Reuse is automatic in `batch-select`: if a previously selected skill scores >= the best new candidate for the current part, it is reused instead of installing another. The output marks reused parts with `"reused": true`.

Do not manually install a duplicate when `batch-select` already determined reuse.

### 6. Install the selected skills

After user confirms the plan, for each non-reused, non-fallback part, install the selected skill:

```bash
python3 <skill_dir>/scripts/skills_router.py install "<owner/repo@skill>" --json
```

Read the output and note:
- `already_installed_before` — if `true`, do NOT remove this skill during cleanup
- `installed_path` — where to find SKILL.md in the next step

Install globally for codex. Install only the selected skill, not whole bundles.

### 7. Use the installed skill

Newly installed skills cannot be hot-loaded by the runtime. Treat them as temporary knowledge packages:

1. **Read** `{installed_path}/SKILL.md` — understand what this skill does
2. **List** `{installed_path}/` — see what else is available (scripts/, references/, agents/)
3. **Read only** the references relevant to the current part — do not load the entire repo into context
4. **Execute only** the scripts relevant to the current part
5. **Follow** the skill's workflow where it is precise; use judgment where it is vague
6. **Record** what was completed with which skill

If the installed skill turns out to be weak, vague, or irrelevant: try the next candidate from the `candidates` list in the batch-select output, or fall back to direct execution.

### 8. Execute parts in order

For each part in the batch-select output:

1. Check `selected` — if null, this part is a fallback; solve it directly
2. Check `reused` — if true, use the already-installed skill from `reused_from_package`; skip installation
3. If `reused` is false and `selected` is non-null: run `install`, then Step 7
4. Complete the part using the skill's guidance
5. Move to the next part

Do not reorder parts unless the user explicitly prefers a different plan.

### 9. Clean up after the full task

After ALL parts are complete, remove each skill that was installed specifically for this task:

```bash
python3 <skill_dir>/scripts/skills_router.py remove "<owner/repo@skill-name>" --json
```

Prefer passing the full package reference for cleanup. `remove "<skill-name>"` is kept only for backward compatibility and will fail if multiple installed skills share the same name.

Only remove skills where `already_installed_before` was `false`. Keep skills that: existed before this task, the user asked to keep, or are still needed by a pending part.

### 10. Fallback rules

- No strong relevant candidate → solve the part directly without an external skill
- Installation fails → explain, try the next candidate, or solve directly
- Selected skill is too weak/vague → try the next candidate from `candidates`, or solve directly
- Cleanup is handled through `skills remove`; do not manually delete skill directories from this router

### 11. Report at the end

Summarize: how you decomposed the request, which parts used skills vs fallback, which skills were selected and why, which were reused, which were newly installed, which were cleaned up, and any limitations or weak matches.

## Safety rules

- Do not install many uncertain skills just to explore
- Prefer the smallest relevant skill for each part
- Do not use external skills for destructive or production-sensitive actions without explicit confirmation
- Prefer relevance first, popularity second
- Avoid repeatedly installing and removing the same skill within one request

## Useful commands

```bash
# Check prerequisites
python3 <skill_dir>/scripts/skills_router.py check --json

# Search for a single query
python3 <skill_dir>/scripts/skills_router.py search "pr review" --json

# Full batch selection with preview (no installation)
python3 <skill_dir>/scripts/skills_router.py batch-select \
  --parts-json '[{"part_id":"p1","title":"Review PR","capability":"review","queries":["pr review"],"needs_skill":true}]' \
  --dry-run --json

# Install and remove
python3 <skill_dir>/scripts/skills_router.py install "owner/repo@skill-name" --json
python3 <skill_dir>/scripts/skills_router.py remove "owner/repo@skill-name" --json

# List installed skills
python3 <skill_dir>/scripts/skills_router.py list --json

# Tune relevance thresholds (default: high=80, medium=30)
python3 <skill_dir>/scripts/skills_router.py select \
  --part-title "PR review" --query "code review" \
  --relevance-high 70 --relevance-medium 25 --json
```

## Read next when needed

- For ranking, decomposition, and data-model details, read `references/v2-design.md`.
