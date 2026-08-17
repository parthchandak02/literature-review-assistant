# LLM provider change — file touch list

Use when adding a provider or renaming the default API key end-to-end.

## Core routing

| File | What to change |
|------|----------------|
| `config/settings.yaml` | All `agents.*.model` (per-role tiering), `rag.hyde_model`, `rag.reranker_model`, `extraction.pdf_vision_model`, `llm.price_fallback_per_mtok` |
| `src/llm/registry.py` | `PREFIX_TO_ENV`, `PREFIX_TO_PROVIDER_ID`, `_provider_with_api_key`, `required_env_keys_from_settings` fallback |
| `src/llm/pydantic_client.py` | Provider-specific structured output / `extra_body` |
| `src/llm/provider.py` | Usually unchanged; cost uses `parse_model_ref` + genai-prices + YAML fallbacks |
| `src/llm/model_fallback.py` | Tier → agent → model from settings only |
| `src/config/loader.py` | Comments + `validate_secret_env` fallback key |
| `src/config/env_context.py` | `resolve_env_overrides()` RunRequest field mapping |

## Web API

| File | What to change |
|------|----------------|
| `src/web/shared.py` | `RunRequest`, `_GenerateConfigRequest` key fields |
| `src/web/routers/config.py` | `_UI_KEY_TO_ENV`, `get_env_keys`, `_mask_secret` placeholders |
| `src/web/routers/run_lifecycle.py` | Form `*_api_key` params, `generate_config_stream` overrides |
| `src/orchestration/helpers/runtime.py` | `llm_available()` environment key list |
| `src/writing/contradiction_resolver.py` | Optional LLM key soft check |
| `src/screening/criteria_refinement.py` | Optional LLM key soft check |
| `scripts/lib/diag_costs.py` | `_classify_model()` provider label |

## Frontend

| File | What to change |
|------|----------------|
| `frontend/src/lib/api/storage.ts` | `StoredApiKeys` interface + `emptyStoredApiKeys()` |
| `frontend/src/lib/api/types.ts` | `RunRequest` |
| `frontend/src/lib/api/config.ts` | Labels, `buildRunRequest`, `generateConfigStream`, default required keys |
| `frontend/src/lib/api/runs.ts` | Multipart form field names |
| `frontend/src/lib/runSession.ts` | Key mapping on run start |
| `frontend/src/components/ApiKeysSection.tsx` | `LLM_FIELDS`, default `requiredKeys` |
| `frontend/src/components/setup/SetupApiKeysSection.tsx` | Primary LLM key field |
| `frontend/src/components/setup/types.ts` | `ConfigGenerateRequest` key field |
| `frontend/src/components/setup/QuestionStage.tsx` | Required key defaults + initial key state |
| `frontend/src/components/setup/ConfigReviewStage.tsx` | Required LLM ui keys default |
| `frontend/src/views/SetupView.tsx` | Pending key state |
| `frontend/src/hooks/useDraftConfigFlow.ts` | Key propagation |
| `frontend/src/hooks/useDraftConfigFlow.test.ts` | Test fixtures |

## Env and docs

| File | What to change |
|------|----------------|
| `.env.example` | Required key section, comments, get-key URLs |
| `README.md` | Setup flow text, API Keys table, cost note |
| `tests/unit/test_llm_registry.py` | Model strings, expected env keys, rate tiers |
| `tests/unit/test_env_context.py` | Override field names, environment variable names |
| `tests/unit/test_pydantic_client_provider_modes.py` | Model strings, thinking-disable cases |
| `tests/unit/test_provider_cost_estimation.py` | If default model strings change |

## Optional / parity-only

- `docs/API.md#rest-endpoints` — only if REST request/response fields change (Section 10.1 parity)
- `docs/ARCHITECTURE.md` — if architecture narrative changes

## Env var ↔ UI key mapping (canonical)

Defined in `src/web/routers/config.py` `_UI_KEY_TO_ENV`:

| UI key | Env var |
|--------|---------|
| `fireworks` | `FIREWORKS_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `mistral` | `MISTRAL_API_KEY` |
| `cohere` | `CO_API_KEY` |

Required UI keys are computed at runtime from `config/settings.yaml` model prefixes via the config env-keys required endpoint.
