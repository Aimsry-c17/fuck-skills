---
name: dynamic-skill-router
description: Analyze a user request, decompose it into ordered capability parts, decide which parts need external skills, search skills.sh for each such part, choose the highest-install relevant skill, temporarily install it for Codex, follow the installed skill's instructions to complete the part, reuse skills when possible, and remove temporary skills after the task. Use when a request spans multiple specialized areas such as review, testing, deployment, migration, documentation, or integration and a small on-demand skill set is preferable to keeping many skills installed permanently.
---

# Dynamic Skill Router

Use this skill when a single user request may require multiple specialized skills and you want to borrow those skills temporarily instead of keeping a large permanent skill set.

## Core idea

Do not treat the whole request as a single search target. Instead:

1. split the request into ordered capability parts
2. decide which parts actually need an external skill
3. search `skills.sh` separately for each skill-worthy part
4. choose the highest-install relevant skill for each part
5. reuse a selected skill across multiple parts when it already covers them well
6. clean up temporary skills after the full task is complete

## Workflow

### 1. Decompose the request into ordered parts

Break the user request into a short list of ordered parts. Each part should represent an independent capability, not just a sentence fragment.

Prefer parts such as:

- review
- testing
- deployment
- documentation
- refactor
- analysis
- migration
- integration

Good example:

- part 1: review the PR
- part 2: add test coverage
- part 3: write the changelog

Bad example:

- split every sentence into tiny pieces
- split by grammar rather than by capability

Preserve execution order. Some requests require a strict sequence such as review -> change -> test -> document.

### 2. Decide which parts need an external skill

For each part, decide whether routing is justified.

Set `needs_skill=true` only when the part is specialized enough that a community skill may provide meaningful leverage and no currently available built-in or local skill is already a good fit.

Set `needs_skill=false` when the part is simple, generic, already covered locally, or cheaper to solve directly.

Examples of parts that often justify external skills:

- framework-specific best practices
- PR review workflows
- testing playbooks
- deployment guides
- changelog or release note generation
- migration procedures

Examples of parts that usually do not justify external skills:

- small text edits
- simple refactors
- basic explanations
- trivial formatting tasks

### 3. Generate queries for each skill-worthy part

For every part with `needs_skill=true`, create 1-3 focused queries.

Prefer combinations like:

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

Do not over-expand queries. A few focused searches are better than broad, noisy exploration.

### 4. Search skills.sh for each part

Use the helper script:

```bash
python3 <skill_dir>/scripts/skills_router.py search "<query>" --json
```

Search separately for each part, not just once for the full request. Merge candidates across that part's queries and deduplicate by skill.

Record for each candidate:

- package
- repo
- skill
- installs
- url
- which queries matched it

## Selection rule

Always use this order:

1. filter for relevance to the current part
2. among the relevant candidates, prefer the highest-install skill

This is **not** "globally hottest skill wins". It is "highest-install relevant skill for this specific part wins".

If top candidates are close in popularity but imply different approaches, ask the user to choose. Otherwise select the top relevant skill automatically and explain why.

### 5. Reuse skills when possible

Before installing a new skill for a later part, check whether an already selected skill can cover that part well enough.

Prefer reuse when:

- the earlier skill already covers the capability
- reuse will not noticeably reduce quality
- the new part does not need a clearly more specialized skill

Avoid redundant installation when one skill can reasonably cover adjacent parts.

### 6. Install temporarily for Codex

Install only the selected skill for the current part:

```bash
python3 <skill_dir>/scripts/skills_router.py install "<owner/repo@skill>" --json
```

Important rules:

- install globally for `codex`
- install only the selected skill, not whole bundles indiscriminately
- record whether the skill already existed before installation
- do not remove skills that existed before the current task
- prefer unified cleanup at the end of the full request, not immediate cleanup after every part

The helper script reports:

- `repo`
- `skill`
- `already_installed_before`
- `installed_path`

### 7. Use the installed skill by reading its files directly

After installation, read the installed skill's `SKILL.md` from the reported `installed_path`.

Then:

1. follow its workflow where it is precise
2. read only the references needed for the current part
3. execute only the scripts relevant to that part
4. avoid loading the whole installed repository into context
5. record what part was completed with which skill

## Important limitation

Newly installed skills may not become immediately available to the runtime skill loader in the same turn. Therefore, do **not** rely on hot-loading the installed skill through the platform's native skill invocation path.

Treat installed skills as temporary knowledge packages:

1. install them
2. read `SKILL.md`
3. selectively read references or run scripts
4. complete the target part
5. clean them up later if they were installed only for this task

This still achieves the goal of temporary skill acquisition, use, and disposal.

### 8. Execute parts in order

Run the request as an ordered sequence of parts.

For each part:

1. determine whether a selected or reusable skill applies
2. install it if needed
3. use its instructions to complete the part
4. mark the part complete
5. continue to the next part

Do not reorder parts unless the user explicitly prefers a different plan.

### 9. Clean up after the full task

Prefer unified cleanup after the whole request is complete.

If and only if `already_installed_before` is `false`, remove the skill after all relevant parts are done:

```bash
python3 <skill_dir>/scripts/skills_router.py remove "<skill-name>" --json
```

Do not remove the skill when:

- the full task is incomplete
- the user asks to keep it installed
- the skill existed before this workflow started
- a later part still needs it

### 10. Fallback rules

If no strong relevant skill exists for a part, solve that part directly.

If installation fails, explain the failure, continue with the next best option when reasonable, or solve the part without the external skill.

If the selected skill turns out to be too weak or too vague, try the next relevant candidate or fall back to direct execution.

### 11. Report clearly

Tell the user:

- how you decomposed the request
- which parts needed skills and which did not
- which queries you used for each part
- which skills were selected and why
- whether any skills were reused across parts
- which skills were newly installed
- which skills were cleaned up afterward
- any limitations, weak matches, or fallback decisions

## Safety rules

- Do not install many uncertain skills just to explore.
- Prefer the smallest relevant skill for each part.
- Do not use external skills for destructive or production-sensitive actions without explicit confirmation.
- Prefer relevance first, popularity second.
- Avoid repeatedly installing and removing the same skill within one request.

## Useful commands

Replace `<skill_dir>` with the absolute path of this skill folder.

```bash
python3 <skill_dir>/scripts/skills_router.py search "pr review" --json
python3 <skill_dir>/scripts/skills_router.py search "react testing" --json
python3 <skill_dir>/scripts/skills_router.py install "wshobson/agents@typescript-advanced-types" --json
python3 <skill_dir>/scripts/skills_router.py remove "typescript-advanced-types" --json
python3 <skill_dir>/scripts/skills_router.py list --json
```

## Read next when needed

- For ranking, decomposition, and data-model details, read `references/v2-design.md`.
- For practical selection heuristics, read `references/selection-heuristics.md`.
