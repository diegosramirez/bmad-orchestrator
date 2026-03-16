**Shortest Path to Value: Redirect Sign-Ups Directly to Product Creation Page**

**Hypothesis** (subtitulo, va en negritas y la letra es mas grande que el contenido)
*(Párrafos descriptivos con la lógica del experimento)*
The dashboard (blank slate) is the largest activation killer. Sending users directly to product creation eliminates the ambiguity of "what do I do now?". 
The success of the first Welcome Page experiment led us to some new designs...

**Intervention** (subtitulo, va en negritas y la letra es mas grande que el contenido)
*(Lista de viñetas con los cambios técnicos a realizar)*
* Regardless of validation status, redirect new vendors directly to `/product/create`.
* Keep the email-validation mandatory banner blocking the final submission.

**Data to Collect**  (subtitulo, va en negritas y la letra es mas grande que el contenido)
*(Lista de viñetas con métricas de éxito)*
* Product creation start rate
* Product creation completion rate
* ... (etc)

**Success Threshold**   (subtitulo, va en negritas y la letra es mas grande que el contenido)
> *(Bloque de cita/blockquote para resaltar el KPI objetivo)*
> +5-10% improvement in product creation start rate over the existing welcome screen.

**Rationale** (subtitulo, va en negritas y la letra es mas grande que el contenido)
*(Explicación conceptual de Product-Led Growth)*
This is the **PLG "Straight Line to Value" principle**...



**Designs**  (subtitulo, va en negritas y la letra es mas grande que el contenido)
* **Enlace:** [New-Landing-Page-Experience — External-Exam-He...](https://www.figma.com)
* **Elemento Visual:** Se observa un preview de imagen con bordes redondeados.
* **Botón de Acción:** `[Connect to Figma]` (Botón azul con bordes redondeados).



**Mechanics**     
**Who sees it:**
* Usuarios específicos (Nuevos sin productos / No descartados).

**Flow:**
* **Condicionales de usuario:** * Si hace click en CTA -> Redirigir a `/product/creation`.
    * Si hace click en Cerrar -> Guardar flag en `localStorage` o `DB`.

**Returning users:**
* Lógica de persistencia de la pantalla de bienvenida.



**Tracking** (subtitulo, va en negritas y la letra es mas grande que el contenido)
*(Estructura de tabla con 3 columnas para analítica)*

| When it Fires (Trigger) | Event Name (ID) | Required Properties (Meta) |
| Welcome gate is rendered | `viewed_welcome_gate` | (no changes) |
| User opts-out | `Opt-Out Clicked` | feature, version, page |
| User clicks CTA | `CTA Clicked` | (vacio) |



**Acceptance Criteria** (subtitulo, va en negritas y la letra es mas grande que el contenido)
*(Tabla compleja de 4 columnas con celdas de color verde en la última columna para "Production Status")*

| Scenario | Criteria (BDD) | QA | Production (Status) |
| **Welcome-Gate Shown** | **Given** [User] **When** [Action] **Then** [Result] | (Vacio) | Confirmed by video |
| **CTA Redirects...** | **Given** [Visibility] **When** [Click] **Then** [Redirect] | (Vacio) | Confirmed by video |
| **Dismiss Loads...** | **Given** [Gate visible] **When** [Dismiss] **Then** [Dashboard] | (Vacio) | Confirmed by video |
| **Feature Flag...** | **Given** [Flag ON/OFF] **Then** [Toggle Behavior] | (Vacio) | Expected behaviour |
| **Event Tracking** | **Given** [Interaction] **Then** [Fire events] | (Vacio) | Shown by tracking results |
| **Design & Resp.** | **Given** [Viewports] **Then** [Match Figma] | (Vacio) | Shown by testing results |

