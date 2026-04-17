# Multi-LLM Provider Abstraction Plan

**Date:** 2026-04-14
**Status:** Planning
**Current State:** All LLM calls hardcoded to Anthropic Claude (API + Agent SDK)

## Goal

Make the BMAD orchestrator's LLM layer interchangeable so it can work with multiple providers (Anthropic Claude, OpenAI/Codex, Google Gemini, etc.) without rewriting node business logic.

---

## Current Architecture

### Two Claude Integration Points

The orchestrator has two separate service classes that talk to Claude, each with very different replaceability profiles.

#### 1. `ClaudeService` (`services/claude_service.py`)

API wrapper for text completion and structured output. Used by planning/orchestration nodes.

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `complete()` | `(system, user, max_tokens, agent_id) -> str` | Text in, text out |
| `complete_structured()` | `(system, user, schema, agent_id) -> PydanticModel` | Text in, validated Pydantic model out (via tool_use + forced tool choice) |
| `classify()` | `(system, user, options) -> str` | Text in, pick one option out (wraps `complete()`) |
| `get_usage_report()` | `() -> dict` | Aggregated token usage stats |

**Anthropic-specific patterns inside this service:**

| Pattern | Location | Replaceability |
|---------|----------|----------------|
| `anthropic.Anthropic()` client | Line ~64 | Trivial — swap client |
| `messages.stream()` streaming | Lines ~96-115 | Moderate — different per LLM |
| `cache_control: {"type": "ephemeral"}` | Lines ~152, 249, 311 | Moderate — Claude-only feature, degrade gracefully |
| Tool-use for structured output (forced tool choice) | Lines ~251-291 | Moderate — all modern LLMs support structured output, but mechanism differs |
| `response.stop_reason == "max_tokens"` | Line ~264 | Low — all LLMs signal truncation |
| `response.usage.input_tokens` / `output_tokens` | Lines ~164-179 | Low — standard across LLMs |
| Multi-turn tool retry on validation failure | Lines ~302-347 | Moderate — logic is generic, message format is SDK-specific |

**Nodes that use this service:**
- `check_epic_state` — `complete_structured()`
- `create_or_correct_epic` — `complete_structured()`
- `create_story_tasks` — `complete_structured()`
- `party_mode_refinement` — `complete()`, `complete_structured()`
- `epic_architect` — `complete_structured()`
- `detect_commands` — `complete()`
- `dev_story` — `complete_structured()` (alongside agent service)
- `dev_story_fix_loop` — `complete()` (alongside agent service)

#### 2. `ClaudeAgentService` (`services/claude_agent_service.py`)

Wraps the **Claude Agent SDK** (Claude Code CLI) for autonomous multi-turn code generation with direct file system access.

**Key dependency:** `claude-agent-sdk>=0.1.40`

**What it does:**
- Spawns an async agentic loop via `claude_agent_sdk.query()`
- Claude gets access to tools: Read, Write, Edit, Bash, Glob, Grep
- Tracks touched files, tool invocations, and cost
- Returns `AgentResult` with generated files and metadata

**Anthropic-specific patterns:**

| Pattern | Replaceability |
|---------|----------------|
| `claude_agent_sdk.query()` async generator loop | Very hard — entire execution model |
| Tool names (`Write`, `Edit`, `Bash`, etc.) specific to Claude Code CLI | Very hard — tied to runtime environment |
| `permission_mode="bypassPermissions"` | Very hard — Claude Code security model |
| `effort="low"` tuning parameter | Hard — Claude Code specific |
| `result_msg.total_cost_usd` cost tracking | Low — can calculate externally |
| `output_format` JSON schema | Moderate — other agent frameworks support this differently |

**Nodes that use this service:**
- `dev_story` — `run_agent()` (code generation)
- `dev_story_fix_loop` — `run_agent()` (fix iteration)
- `code_review` — `run_agent()` (review)
- `qa_automation` — `run_agent()` (test generation)
- `e2e_automation` — `run_agent()` (E2E test generation)
- `e2e_fix_loop` — `run_agent()` (E2E fix iteration)

### What's Already Well-Architected

- **All Anthropic SDK imports are confined to two service files** — zero leakage into nodes or business logic
- **Jira, GitHub, and Slack already use Protocol + factory pattern** (`protocols.py`, `service_factory.py`) — the LLM services just weren't given the same treatment
- **Node factory pattern** (`make_*_node(service, settings)`) means nodes receive services as arguments — dependency injection is already in place
- **Single composition root** in `graph.py` (`build_graph()`) — one place to swap service instantiation

### What's Missing

- No `LLMServiceProtocol` in `protocols.py`
- No `AgentServiceProtocol` in `protocols.py`
- No `create_llm_service()` factory in `service_factory.py`
- `ClaudeService` and `ClaudeAgentService` are hardcoded in `graph.py`
- Config assumes single provider (`anthropic_api_key`, `model_name` = claude model)

---

## Coupling Difficulty Matrix

### Easy to Abstract (~30% of LLM surface)

| Feature | Current Location | Notes |
|---------|-----------------|-------|
| Text completion I/O | `ClaudeService.complete()` | Standard across all LLMs |
| Classification / option picking | `ClaudeService.classify()` | Wraps `complete()`, free |
| Token usage tracking | `response.usage.*` | All LLMs return token counts |
| Truncation detection | `response.stop_reason` | All LLMs signal this |
| Model name config | `config.py` | Just strings |
| API key config | `config.py` | Parametrize per provider |

### Moderate Effort (~40% of LLM surface)

| Feature | Current Location | Notes |
|---------|-----------------|-------|
| Structured output (text -> Pydantic) | `ClaudeService.complete_structured()` | Uses Claude tool_use; OpenAI has function_calling; Gemini has structured output. All doable, mechanism differs. |
| Streaming | `messages.stream()` event loop | Each SDK has its own streaming API |
| Prompt caching | `cache_control: {"type": "ephemeral"}` | Claude-only; degrade gracefully for other providers |
| Validation retry loop | Multi-turn tool retry | Logic is provider-agnostic; message format is not |
| Per-agent model routing | `config.py` agent_models dict | Needs provider-aware model name mapping |
| Pydantic schema -> LLM instruction | All nodes via `complete_structured()` | Schema is standard; delivery mechanism varies |

### Very Hard (~30% of LLM surface)

| Feature | Current Location | Notes |
|---------|-----------------|-------|
| Claude Agent SDK agentic loop | `ClaudeAgentService` entire class | No equivalent exists in other ecosystems with same tool surface |
| File system tool access (Read/Write/Edit/Bash) | Agent SDK tool set | Tied to Claude Code CLI runtime |
| Async agent execution model | `query()` async generator | Fundamental architecture difference |
| Agent cost/usage tracking | `result_msg.total_cost_usd` | SDK-specific reporting |

---

## Implementation Plan

### Phase 1 — Protocol + Factory Layer (No behavior change)

**Effort:** Small
**Files touched:** `protocols.py`, `service_factory.py`, `graph.py`, `config.py`

Create the abstraction layer without changing any behavior:

1. **Add `LLMServiceProtocol` to `protocols.py`:**

```python
class LLMServiceProtocol(Protocol):
    def complete(
        self, system_prompt: str, user_message: str,
        *, max_tokens: int = ..., agent_id: str | None = None,
    ) -> str: ...

    def complete_structured(
        self, system_prompt: str, user_message: str,
        schema: type[T], *, max_tokens: int = ..., agent_id: str | None = None,
    ) -> T: ...

    def classify(
        self, system_prompt: str, user_message: str,
        options: list[str], *, agent_id: str | None = None,
    ) -> str: ...

    def get_usage_report(self) -> dict[str, Any]: ...
```

2. **Add `AgentServiceProtocol` to `protocols.py`:**

```python
class AgentServiceProtocol(Protocol):
    async def run_agent(
        self, prompt: str, *,
        allowed_tools: list[str] | None = None,
        output_format_schema: type[BaseModel] | None = None,
        agent_id: str | None = None,
    ) -> AgentResult: ...

    def get_usage_report(self) -> dict[str, Any]: ...
```

3. **Add `create_llm_service()` factory to `service_factory.py`:**

```python
def create_llm_service(settings: Settings, **kwargs) -> LLMServiceProtocol:
    # For now, always returns ClaudeService. The factory exists
    # so graph.py doesn't hardcode the concrete class.
    return ClaudeService(settings, **kwargs)
```

4. **Update `graph.py`** to use the factory instead of `ClaudeService(...)` directly.

5. **Add `llm_provider` to `Settings`** (default `"anthropic"`, no behavior change).

### Phase 2 — Second Provider Adapter

**Effort:** Medium
**Prerequisite:** Phase 1

Implement a second provider to validate the abstraction:

1. **Create `openai_service.py`** (or `litellm_service.py`) implementing `LLMServiceProtocol`:
   - `complete()` via `client.chat.completions.create()`
   - `complete_structured()` via function calling or `response_format={"type": "json_schema", ...}`
   - Token tracking via `completion.usage`

2. **Update factory** to route based on `settings.llm_provider`.

3. **Update config** to support provider-specific API keys and model names:

```python
# config.py additions
llm_provider: str = "anthropic"  # or "openai", "gemini", "litellm"
openai_api_key: SecretStr | None = None
google_api_key: SecretStr | None = None
```

4. **Handle provider-specific features gracefully:**
   - Prompt caching: only apply for Anthropic; no-op for others
   - Streaming: implement per provider or disable for unsupported ones

This covers **~70% of nodes** — all the planning/orchestration ones that only use `ClaudeService`.

### Phase 3 — Agent Service Abstraction (Future)

**Effort:** Large
**Prerequisite:** Phase 2, and alternative agent runtimes maturing

The `ClaudeAgentService` wraps Claude Code's agentic loop — there's no drop-in replacement today. Options to evaluate when ready:

| Approach | Pros | Cons |
|----------|------|------|
| **Keep Claude Agent SDK as-is** | Works now, battle-tested | Vendor lock for code gen nodes |
| **OpenAI Codex CLI** | Similar concept (agent + tools) | Different tool surface, less mature |
| **Custom Langchain/LangGraph agent** | Provider-agnostic, full control | Significant build effort, tool setup |
| **Hybrid: Claude for agents, other for planning** | Pragmatic, incremental | Two providers to manage |

**Recommended near-term:** Keep Claude Agent SDK for code generation nodes. Abstract only the planning/orchestration layer (Phases 1-2). Revisit agent abstraction as competing agent SDKs mature.

### Optional: `litellm` / `instructor` Shortcut

Instead of writing per-provider adapters manually, consider:

- **[`litellm`](https://github.com/BerriAI/litellm):** Unified API across 100+ LLM providers. Single `completion()` call that routes to any backend. Handles streaming, token tracking, model mapping. Trade-off: extra dependency, less control over provider-specific features (caching).
- **[`instructor`](https://github.com/instructor-ai/instructor):** Wraps any LLM client to provide validated Pydantic structured output. Would replace the custom tool_use structured extraction in `complete_structured()`. Trade-off: extra dependency, but eliminates the hardest abstraction problem.

Using either would collapse Phases 1+2 into a single step for the `LLMServiceProtocol` side.

---

## Files Impact Summary

| File | Phase | Change |
|------|-------|--------|
| `services/protocols.py` | 1 | Add `LLMServiceProtocol`, `AgentServiceProtocol` |
| `services/service_factory.py` | 1 | Add `create_llm_service()` factory |
| `graph.py` | 1 | Use factory instead of `ClaudeService(...)` |
| `config.py` | 1-2 | Add `llm_provider`, optional provider API keys |
| `services/openai_service.py` | 2 | New file: OpenAI adapter implementing protocol |
| `services/claude_service.py` | 1 | No change (already conforms to protocol shape) |
| `services/claude_agent_service.py` | 3 | Future: conform to `AgentServiceProtocol` |
| Node files (`nodes/*.py`) | None | Zero changes — they receive services via dependency injection |

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Structured output quality varies across LLMs | High | Validation retry loop handles this; may need more retries for weaker models |
| Prompt caching loss increases cost/latency | Medium | Cache control is a no-op for non-Anthropic; accept the cost or find provider-specific equivalents |
| Different LLMs produce different quality personas | Medium | Test each persona prompt with target LLM; may need provider-specific prompt tuning |
| Agent SDK has no replacement | High (near-term) | Keep Claude Agent SDK for code gen; only abstract planning layer first |
| `litellm` / `instructor` adds supply chain risk | Low | Both are well-maintained, widely adopted |

---

## Decision Record

**Decision needed:** Which approach for Phase 2?

| Option | Effort | Dependencies | Coverage |
|--------|--------|-------------|----------|
| A. Hand-written per-provider adapters | Higher | None | Full control |
| B. `litellm` wrapper | Lower | +1 dependency | 100+ providers instantly |
| C. `instructor` + per-provider client | Medium | +1 dependency | Best structured output story |
| D. `litellm` + `instructor` combo | Lowest | +2 dependencies | Maximum coverage + quality |
