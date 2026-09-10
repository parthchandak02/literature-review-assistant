# Review Type Decision Wizard

Dr. Chandak flowchart implemented in `frontend/src/components/setup/ReviewTypeDecisionStage.tsx`.

## User POV

1. New Review (+) → first screen asks if the question is **broad**
2. Broad + map evidence → **scoping review**
3. Narrow + intervention/outcome focus + determine what evidence shows → **systematic review**
4. Not sure → guidance panel with examples, manual pick

## Driving verification

```bash
cd frontend && pnpm exec vitest run ReviewTypeDecisionStage
```

## Outputs

- `ReviewTypeChoice`: `"scoping" | "systematic"`
- Passed to `QuestionStage` → `ConfigGenerateRequest.reviewType` → API `review_type`

## Gotchas

- Reuse past config / Paste YAML skips the wizard (power-user paths).
- `health_sdg` profile works for both review types.
