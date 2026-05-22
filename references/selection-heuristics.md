# Selection heuristics

Use this reference when the main workflow in `SKILL.md` needs more concrete selection guidance.

## Selection principle

Always use this order:

1. relevance to the current part
2. install popularity within the relevant set

Do not choose the globally hottest skill if it is not clearly relevant to the current part.

## Prefer these kinds of external skills

- framework-specific best practices
- deployment or release workflows
- review and audit playbooks
- testing playbooks
- changelog or release-note generators
- migration and integration helpers

## Avoid these kinds of external skills

- huge umbrella repos when a smaller focused skill exists
- low-signal matches with vague names
- skills that imply risky production actions without review
- skills whose instructions duplicate common knowledge
- multiple overlapping skills for adjacent parts when one already covers them well

## Part decomposition hints

Split by capability, not by sentence.

Good capability buckets:

- review
- testing
- deployment
- documentation
- analysis
- migration
- integration
- refactor

Avoid over-splitting. A single request should usually become a short ordered list, not dozens of micro-parts.

## Query expansion ideas

Turn each skill-worthy part into 1-3 focused searches:

- noun form: `deploy`, `review`, `migration`
- tool form: `jest testing`, `vercel deploy`
- framework form: `react testing`, `nextjs performance`
- quality form: `best practices`, `security`, `release notes`

## Reuse policy

Prefer reusing an already selected skill when:

- it already covers the current part well
- reuse reduces installation churn
- the new part does not require a significantly more specialized skill

Prefer a new skill only when it materially improves quality for that part.

## Cleanup policy

Prefer unified cleanup after the full request is complete.

Remove only skills installed specifically for the current task.
Keep skills that:

- existed before the task
- were explicitly requested to remain installed
- will be reused by later parts in the same request
