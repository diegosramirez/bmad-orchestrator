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
- Implementation checklists (every service class, every route) — that invites treating the epic as a backlog of layers. The epic itself should stay a charter; **Generate Stories** (`stories_breakdown`) may still produce a small number of **intentional** parallel stories (e.g. backend API vs frontend with mocks) when boundaries and a shared API contract are clear — that is not the same as pasting a layer-by-layer spec here.
- Pasting a full architecture inventory; Epic Architect adds a **concise** `# Architecture` block separately.

## Shape in BMAD

After Discovery, the description usually starts with `# Discovery` and short `##` subsections (e.g. Overview, Goals, User Value, Scope). After Epic Architect, `# Architecture` is appended with a brief structured block — still **scannable**, not a novel.

## Stories vs Epics

- **Epic** = charter, boundaries, and outcome themes.
- **Story** = smallest useful BMAD unit for implementation. **Generate Stories** defaults to **two** stories (backend API/data + frontend with mocks) when Discovery and Architecture describe both a client app and a server/API. Use a **single** story when the epic is one surface or a small cohesive change. Use the story template in `docs/template-jira.md`.
