> **Purpose:** Jira **Epics** are short charters. A reader should grasp **what**, **why**, and the **general solution direction** in a few minutes — not wade through dozens of requirements or a full technical design. Fine-grained detail belongs in **Stories** (`docs/template-jira.md`), architecture notes, or linked docs.

## What to cover (high level)

| Theme | Guidance |
| --- | --- |
| **What** | One clear product or capability outcome. |
| **Why** | User or business need; why this work matters now. |
| **Solution (abstract)** | Broad technical approach (e.g. client-side app with embedded data, BFF + REST) — not a component-by-component spec. |
| **Out of scope** | Explicit non-goals to prevent scope creep. |
| **Acceptance (epic level)** | Only **non‑negotiable**, testable themes — not 50 micro-requirements. |

## What to avoid in the Epic body

- Exhaustive functional requirement lists (cap bullets; prefer “absolute needs”).
- Implementation checklists (every service class, every route) — that invites horizontal “layer” tickets later.
- Pasting a full architecture inventory; Epic Architect adds a **concise** `# Architecture` block separately.

## Shape in BMAD

After Discovery, the description usually starts with `# Discovery` and short `##` subsections (e.g. Overview, Goals, User Value, Scope). After Epic Architect, `# Architecture` is appended with a brief structured block — still **scannable**, not a novel.

## Stories vs Epics

- **Epic** = charter, boundaries, and outcome themes.
- **Story** = vertical slice (deliver user-visible value with whatever layers apply); use the story template in `docs/template-jira.md`.
