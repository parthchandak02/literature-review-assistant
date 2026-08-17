---
name: llm-provider
description: Switches default LLM provider or API keys (Fireworks, Gemini, OpenRouter, DeepSeek, etc.) across settings, registry, web API, frontend, and .env. Use when changing model routers, provider prefixes, FIREWORKS_API_KEY, migrating off DeepSeek, adding a new PydanticAI provider, or fixing missing-key / model-not-found LLM errors.
disable-model-invocation: true
---

# LLM Provider and API Key Changes

Prefix-based routing, not a separate router class. Model strings in `config/settings.yaml` drive everything.

```
agents.*.model  →  src/llm/registry.py  →  environment key + PydanticAI provider  →  API call
```

## Current defaults (as of Fireworks migration)

`config/settings.yaml` is the single source of truth for which model each agent uses. Defaults follow a **task-tier** pattern (not one model for everything):

| Tier | Role | Typical agents / settings keys | Env key |
|------|------|-------------------------------|---------|
| Bulk / flash | High-volume structured JSON (screening, batch rank, HyDE, rerank) | `agents.screening_*`, `agents.batch_screener`, `rag.hyde_model`, `rag.reranker_model` | `FIREWORKS_API_KEY` |
| Quality / pro | Reasoning + extraction + RoB + writing | `agents.extraction`, `agents.quality_assessment`, `agents.writing`, etc. | `FIREWORKS_API_KEY` |
| Vision / multimodal | PDF page table extraction (must accept image/PDF input) | `extraction.pdf_vision_model` when `use_pdf_vision: true` | `FIREWORKS_API_KEY` or `GEMINI_API_KEY` |
| Diagram images | Native image generation + vision critique | `agents.research_diagram_drawing`, `agents.research_diagram_critic` | `GEMINI_API_KEY` |
| Embeddings | Local dense retrieval | `rag.embed_model` | none (local) |

Example tier strings today (verify live before shipping): flash bulk uses a dated Fireworks id like `deepseek-v4-flash-0731`; quality uses `deepseek-v4-pro`; PDF vision uses a **vision-capable** Fireworks model (not text-only DeepSeek chat).

Fireworks base URL: `https://api.fireworks.ai/inference/v1` (OpenAI-compatible). Key: `FIREWORKS_API_KEY` (`fw_...`).

**Model ID caveat:** Fireworks serverless ids are often dated (e.g. `deepseek-v4-flash-0731`, not `deepseek-v4-flash`). Always verify ids against the live API before shipping settings changes.

**Modality caveat:** `extraction.pdf_vision_model` must support multimodal input (PDF/image). Text-only chat models (e.g. DeepSeek V4 Pro) will fail or silently skip vision extraction.

**Cost fallback caveat:** `llm.price_fallback_per_mtok` must use **Fireworks serverless** rates when routing through `fireworks:`, not DeepSeek-direct API rates (Pro tier is ~4x higher on Fireworks).

## Workflow checklist

Copy and track:

```
- [ ] 1. Pick provider + model ids per task tier (official docs + live probe)
- [ ] 1b. Confirm modality: text-only vs vision for pdf_vision_model; structured-output quirks per model family
- [ ] 2. Update config/settings.yaml model strings + price_fallback_per_mtok (Fireworks serverless rates)
- [ ] 3. Update src/llm/registry.py if new prefix
- [ ] 4. Update src/llm/pydantic_client.py if provider-specific structured-output quirks
- [ ] 5. Update .env.example + operator .env (never commit .env)
- [ ] 6. Wire web env overrides + config API (backend)
- [ ] 7. Wire frontend StoredApiKeys + setup/run forms
- [ ] 8. Update README.md API key table
- [ ] 9. Update unit tests (registry, env_context, pydantic_client)
- [ ] 10. Smoke test live API + pytest + pm2 restart litreview-api --update-env
```

## Step 1: Verify model ids (required)

Do not trust docs alone. List models and probe:

```bash
uv run python -c "from dotenv import load_dotenv; load_dotenv()"
curl -s -H "Authorization: Bearer ${FIREWORKS_API_KEY}" \
  "https://api.fireworks.ai/inference/v1/models" | python3 -c "
import json,sys
for m in sorted(json.load(sys.stdin).get('data',[]), key=lambda x: x.get('id','')):
    if 'deepseek' in m.get('id','').lower() or 'flash' in m.get('id','').lower():
        print(m['id'])
"
```

Smoke one call per tier (text flash, text pro, and vision model if `use_pdf_vision`):

```bash
uv run python -c "
from dotenv import load_dotenv
load_dotenv()
from src.llm.registry import build_agent
import asyncio
m = 'fireworks:accounts/fireworks/models/deepseek-v4-flash-0731'
async def main():
    r = await build_agent(m).run('Reply: ok')
    print(r.output)
asyncio.run(main())
"
```

404 `Model not found` → wrong id for this account; pick an id from the list endpoint.

## Step 2: config/settings.yaml

Change every model reference:

- `agents.<name>.model`
- `rag.hyde_model`, `rag.reranker_model` (when enabled)
- `extraction.pdf_vision_model` (when `use_pdf_vision: true`)

Add `llm.price_fallback_per_mtok` keys for bare model refs returned by `parse_model_ref()` (both short names and full `accounts/fireworks/models/...` paths if needed).

Rate tiers (`flash` / `pro`) come from `rate_tier_for_model()` in `registry.py` (substring heuristics on model name). When assigning different models per agent, check the derived tier: pro-tier models on high-volume agents hit the 20 RPM internal cap.

Agents can intentionally use different models per role. When retiering, consider: call volume, structured JSON vs prose, context length, multimodal needs, and cost share (extraction/quality dominate spend; screening is usually <1% with batch pre-rank).

## Step 3: New provider prefix (only if not already in registry)

Edit `src/llm/registry.py`:

1. `PREFIX_TO_ENV` — prefix → environment variable name
2. `PREFIX_TO_PROVIDER_ID` — prefix → genai-prices provider id
3. `_provider_with_api_key()` — construct PydanticAI provider (check `pydantic_ai.providers` package first)
4. `required_env_keys_from_settings()` fallback default key if empty

Confirm PydanticAI support:

```bash
uv run python -c "import pkgutil, pydantic_ai.providers as p; print([m.name for m in pkgutil.iter_modules(p.__path__)])"
```

## Step 4: Structured output quirks

`src/llm/pydantic_client.py`:

- Gemini (`google:`): `NativeOutput`
- DeepSeek direct + Fireworks-hosted DeepSeek: disable thinking via `extra_body` for structured calls
- Others: default `ToolOutput`

Extend `_needs_thinking_disabled()` when a new host exposes DeepSeek V4 thinking mode.

## Step 5: Environment files

`.env.example`: document required key at top of LLM section with get-key URL.

Operator local dotenv file: place key in LLM section; remove obsolete keys when fully migrated.

Never commit the local dotenv file. Required keys are **derived** from model prefixes in settings, not hardcoded in loader.

## Step 6–7: Web + frontend plumbing

Backend touch points (see [reference.md](reference.md)):

- `src/config/env_context.py` — `resolve_env_overrides()` field → environment variable
- `src/web/shared.py` — `RunRequest` + `_GenerateConfigRequest` fields
- `src/web/routers/config.py` — `_UI_KEY_TO_ENV`, `get_env_keys`, mask placeholders
- `src/web/routers/run_lifecycle.py` — Form fields, config-generate overrides, fallback required key
- `src/orchestration/helpers/runtime.py` — `llm_available()` key list
- Soft checks: `src/writing/contradiction_resolver.py`, `src/screening/criteria_refinement.py`

Frontend touch points:

- `frontend/src/lib/api/storage.ts` — `StoredApiKeys`
- `frontend/src/lib/api/types.ts` — `RunRequest`
- `frontend/src/lib/api/config.ts` — labels, `buildRunRequest`, `generateConfigStream`, default required ui key
- `frontend/src/lib/api/runs.ts` — multipart form field names
- `frontend/src/lib/runSession.ts`
- `frontend/src/components/ApiKeysSection.tsx`
- `frontend/src/components/setup/*` — setup flow keys and defaults

UI key id (e.g. `fireworks`) must match `_UI_KEY_TO_ENV` in `config.py`.

## Step 8–9: Docs and tests

- `README.md` — API Keys table + setup instructions
- `tests/unit/test_llm_registry.py`
- `tests/unit/test_env_context.py`
- `tests/unit/test_pydantic_client_provider_modes.py`

## Step 10: Verify

```bash
uv run pytest tests/unit/test_llm_registry.py tests/unit/test_env_context.py tests/unit/test_pydantic_client_provider_modes.py -q
./scripts/ops_pm2.sh restart --backend-only   # or: pm2 restart litreview-api --update-env
pm2 list   # confirm litreview-api online
cd frontend && ./node_modules/.bin/tsc -b --noEmit   # after frontend key changes
```

Frontend production: `cd frontend && pnpm build` before production URL checks.

## Switching providers (quick reference)

| Provider | Prefix | Env var | Notes |
|----------|--------|---------|-------|
| Fireworks (default) | `fireworks:` | `FIREWORKS_API_KEY` | OpenAI-compatible; use full `accounts/fireworks/models/...` ids |
| Google Gemini | `google:` → normalized to `google-gla:` | `GEMINI_API_KEY` | Required for diagram image agents |
| DeepSeek direct | `deepseek:` | `DEEPSEEK_API_KEY` | Legacy; thinking disable in pydantic_client |
| OpenRouter | `openrouter:` | `OPENROUTER_API_KEY` | `vendor/model` ref after prefix |
| OpenAI | `openai:` | `OPENAI_API_KEY` | |
| Anthropic | `anthropic:` | `ANTHROPIC_API_KEY` | |

OpenRouter model example: `openrouter:deepseek/deepseek-v4-flash`

## Anti-patterns

- Do not hardcode model id strings in `src/` (only `config/settings.yaml`)
- Do not patch `runs/` artifacts to fix provider behavior
- Do not assign text-only models to `extraction.pdf_vision_model`
- Do not use DeepSeek-direct pricing in `price_fallback_per_mtok` for Fireworks-hosted models
- Do not assume `deepseek-v4-flash` works on Fireworks without probing (dated ids common)
- Do not skip `pm2 restart litreview-api --update-env` after backend `src/` or local dotenv changes
- Do not remove `deepseek:` registry entries unless intentionally dropping support

## Additional resources

- Full file touch list: [reference.md](reference.md)
- Architecture: `docs/ARCHITECTURE.md` (LLM section)
- Official Fireworks docs: https://docs.fireworks.ai/guides/querying-text-models
