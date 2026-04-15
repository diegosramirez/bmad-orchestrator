> **Objetivo del formato:** En las historias se mantiene **detalle fino** (*fine-grained*) para legibilidad operativa: el ingeniero debe saber **qué implementar y cómo validarlo** sin que el ticket sea ilegible. Prioriza listas y tablas escaneables; la narrativa de producto va breve; enlaza documentación larga fuera del cuerpo cuando aplique.

**Shortest Path to Value: Redirect Sign-Ups Directly to Product Creation Page**

**Hypothesis**

*(1–2 párrafos: problema, por qué importa, qué se prueba.)*

The dashboard (blank slate) is the largest activation killer. Sending users directly to product creation eliminates the ambiguity of "what do I do now?". The success of the first Welcome Page experiment led us to some new designs.

**Intervention**

*(Cambios técnicos o de producto concretos; una viñeta = una acción verificable.)*

* Regardless of validation status, redirect new vendors directly to `/product/create`.
* Keep the email-validation mandatory banner blocking the final submission.

**Data to Collect**

*(Métricas o fuentes de datos; suficiente para analítica, sin repetir el dashboard entero aquí.)*

* Product creation start rate
* Product creation completion rate
* (añade solo las que esta historia habilita o afecta)

**Success Threshold**

> *(Un bloque de cita con el KPI o umbral acordado.)*
> +5–10% improvement in product creation start rate over the existing welcome screen.

**Rationale**

*(Opcional y breve: principio de negocio o constraint; evita duplicar lo ya dicho en Hipótesis.)*

This is the **PLG "Straight Line to Value" principle**: reduce steps between sign-up and first value.

**Designs**

* **Link:** [New landing — Figma](https://www.figma.com/example)
* **Visual:** Rounded preview; primary CTA visible above the fold.
* **Action:** `[Connect to Figma]` or attach exported frames if offline.

**Mechanics**

*(Segmentación, flujo paso a paso y ramas; numerar ayuda más que una sola viñeta anidada.)*

**Who sees it**

* New vendors with no products yet; not in the discarded cohort.

**Primary flow**

1. User lands after sign-up → redirect to `/product/create` (or agreed route).
2. If welcome gate is shown → CTA advances; dismiss persists state as specified.

**Branches**

* **CTA:** navigate to `/product/create` (match Intervention).
* **Dismiss:** persist flag in `localStorage` or DB (specify which).

**Returning users**

* Persist welcome-screen dismissal so repeat visits match product rules (define in one line).

**Tracking**

*(Tabla compacta: trigger, nombre de evento, propiedades mínimas.)*

| When it fires (trigger) | Event name | Required properties |
| Welcome gate is rendered | `viewed_welcome_gate` | (unchanged vs baseline) |
| User opts out | `opt_out_clicked` | `feature`, `version`, `page` |
| User clicks CTA | `cta_clicked` | As in tracking spec |

**Acceptance Criteria**

*(**Detalle fino** en la columna BDD: cada fila = un escenario comprobable. Dos columnas para que la tabla siga siendo usable en Jira. Evidencia en staging/producción: comentario del ticket, subtarea de QA o enlace, no hace falta repetirla por fila.)*

| Scenario | Given / When / Then (fine-grained) |
| Welcome gate visibility | **Given** a new eligible user **when** they complete sign-up **then** they are redirected per Intervention and (if applicable) see the gate only per Mechanics. |
| CTA redirect | **Given** the gate is visible **when** the user clicks the primary CTA **then** the app navigates to `/product/create` (or specified route). |
| Dismiss and persistence | **Given** the gate is visible **when** the user dismisses it **then** state persists per Mechanics and the user reaches the expected next screen. |
| Feature flag | **Given** the flag is ON vs OFF **then** behavior matches the flag matrix (link or bullet list if non-trivial). |
| Analytics | **Given** each listed interaction **then** the corresponding event fires with required properties from Tracking. |
| Design / responsive | **Given** target viewports **then** UI matches linked designs within agreed tolerance. |
