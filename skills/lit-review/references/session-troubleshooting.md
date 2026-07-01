# Lit Review Session Troubleshooting Tips

Appendix to the main lit-review skill. Contains edge cases discovered during live runs.

## Web of Science Connector Failure

Clarivate WoS API frequently returns status 512 (internal server error). The connector retries 3 times with exponential backoff (5s, 10s, 20s), adding ~35s of delay to phase 2. Remove `web_of_science` from `target_databases` in `config/review.yaml` before launching fresh runs. The pipeline degrades gracefully with "connector_degraded" fallback.

## DeepSeek API Timeout After Phase 2

On the first attempt the pipeline hung after phase 2 search completed during protocol generation. The process consumed high RAM with an active HTTPS connection but produced zero DB writes for 15+ minutes. Fix: kill the process and resume (`uv run python -m src.main resume --workflow-id wf-NNNN`). The second attempt usually succeeds.

## Screening Throughput

Approximately 10 papers/minute during dual-review (DeepSeek batch LLM calls). For 3,000 papers expect 20-30 minutes for Phase 3. The tmux progress bar goes stale — query the runtime DB directly for real status:

```bash
sqlite3 runs/YYYY-MM-DD/wf-NNNN-*/run_*/runtime.db "SELECT decision, COUNT(*) FROM screening_decisions GROUP BY decision;"
sqlite3 runs/YYYY-MM-DD/wf-NNNN-*/run_*/runtime.db "SELECT id, phase_id, phase_label, status FROM workflow_steps ORDER BY id;"
```
