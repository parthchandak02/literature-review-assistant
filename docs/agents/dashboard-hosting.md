# LitReview dashboard hosting

Public URL: `https://litreview.parthchandak.info` (local API `:8001`, Vite HMR `:5173`).
Same ops shape as jobwright: **PM2** for api + ui + tunnel, plus `./scripts/ops_pm2.sh`.

## App surfaces (product)

The public URL is the **systematic review web UI**, not a separate app. Agents should treat these as first-class:

| Surface | Behavior |
|---------|----------|
| **New Review** | Sidebar `+` starts config generation from a research question |
| **Activity** | Live SSE phase timeline, screening log, stop/resume controls |
| **Data / Cost / Results / References** | Run-scoped DB views, cost ops, manuscript readiness, paper PDFs |
| **Export** | Submission packaging (IEEE LaTeX, DOCX, PRISMA checklist) |

Public traffic is the Cloudflare tunnel → `:8001` serving `frontend/dist`. Vite HMR (`:5173`) is local only. Rebuild production UI with `./scripts/ops_pm2.sh restart --prod-ui` (or `make deploy-prod`).

## Local hot-reload (recommended for testing)

```bash
cd /Volumes/ExternalSSD/Projects/literature-review-assistant
uv sync
cd frontend && pnpm install && cd ..

# First time: copy PM2 config
cp ecosystem.config.example.js ecosystem.config.js

# Start / restart API (:8001) + Vite (:5173, HMR)
./scripts/ops_pm2.sh restart

# Open the hot-reloading UI
open http://127.0.0.1:5173
```

| Command | What it does |
|---------|----------------|
| `./scripts/ops_pm2.sh restart` | Restart `litreview-api` + `litreview-ui` |
| `./scripts/ops_pm2.sh restart --backend-only` | API only (after `src/` changes if not using `--reload`) |
| `./scripts/ops_pm2.sh restart --frontend-only` | Vite only |
| `./scripts/ops_pm2.sh restart --tunnel-only` | cloudflared only |
| `./scripts/ops_pm2.sh restart --all` | api + ui + tunnel |
| `./scripts/ops_pm2.sh restart --prod-ui` | `pnpm build` + restart API + health check |
| `./scripts/ops_pm2.sh restart --status` | `pm2 list` |
| `make pm2-restart` | Makefile alias for default restart |

### Ports

| Service | Port | Notes |
|---------|------|--------|
| API | `8001` | jobwright uses `8002` |
| Vite UI | `5173` | jobwright uses `5120`; proxies `/api` → `8001` |
| Prod SPA | same `8001` | FastAPI serves `frontend/dist` after `--prod-ui` |

### Hot reload notes

- **Frontend:** Vite HMR on `:5173` updates instantly. Use this URL while developing.
- **Backend:** PM2 does not hot-reload by default. After editing Python, run `./scripts/ops_pm2.sh restart --backend-only` (or use plain `uvicorn --reload` in a terminal).
- **Production URL** (`litreview.parthchandak.info`): rebuild with `./scripts/ops_pm2.sh restart --prod-ui`.
- **Do not** restart `litreview-ui` expecting the public site to update; PM2 `litreview-ui` is dev-only. Public traffic hits `litreview-api` + `frontend/dist`.

---

## Production: Cloudflare tunnel + Zero Trust

### 1. Tunnel + DNS

Tunnel UUID and credentials live in `cloudflared-config-litreview.yml`:

```yaml
tunnel: 88118eea-3a0b-4658-8d01-6bfb31ca1cd7
credentials-file: ~/.cloudflared/88118eea-3a0b-4658-8d01-6bfb31ca1cd7.json

ingress:
  - hostname: litreview.parthchandak.info
    service: http://localhost:8001
  - service: http_status:404
```

### 2. PM2 (prod)

For production, edit `ecosystem.config.js` and **do not rely on `litreview-ui`** (API serves `frontend/dist` on `:8001`).

```bash
./scripts/ops_pm2.sh restart --prod-ui   # build + restart api + health
pm2 save
# Optional tunnel:
./scripts/ops_pm2.sh restart --tunnel-only
```

Process names: `litreview-api`, `litreview-ui` (dev only), `litreview-tunnel`.

### 3. Cloudflare Zero Trust (dashboard only)

Access app: **LitReview** (`14b66fe8-f271-4d64-b858-5b0533d76a19`) on `litreview.parthchandak.info`.

1. Zero Trust → Access → Applications → Self-hosted
2. Domain: `litreview.parthchandak.info`
3. Policy: Allow + email allow list (Owner policy)
4. **Session duration:** set Application session to **30 days** (`720h`) so household devices re-auth monthly, not daily. Dashboard: Application → Configure → Session Duration.

CLI (requires a Cloudflare API token with Access edit scope; load credentials the same way as jobwright `docs/agents/dashboard-hosting.md`):

```bash
# Application session (720h = 30 days)
cloudflare-pp-cli accounts access applications-update-an-application \
  14b66fe8-f271-4d64-b858-5b0533d76a19 "$CLOUDFLARE_ACCOUNT_ID" \
  --body-json '{"type":"self_hosted","name":"LitReview","domain":"litreview.parthchandak.info","session_duration":"720h","app_launcher_visible":true,"destinations":[{"type":"public","uri":"litreview.parthchandak.info"}],"allowed_idps":[]}' \
  --agent --yes

# Reusable Owner policy session (same TTL)
cloudflare-pp-cli accounts access policies-update-an-reusable-policy \
  "$CLOUDFLARE_ACCOUNT_ID" 2d15ec50-a1db-4ffd-81b4-0eecdaf9cb0d \
  --decision allow --name Owner --session-duration 720h \
  --include '[{"email":{"email":"parth.chandak02@gmail.com"}},{"email":{"email":"alakaom@gmail.com"}}]' \
  --agent --yes
```

Optional: Zero Trust → Settings → Authentication → Global session duration → match (7–30d). WhatsApp in-app browser uses a separate cookie jar; users may OTP once per in-app context even with 30d app session.

No app code changes are required. Tunnel + Access stay as-is; only session TTL changes.

### 4. Verify

```bash
curl -sf http://127.0.0.1:8001/api/health
# Browser: https://litreview.parthchandak.info  → email OTP → LitReview UI
# Or local HMR: http://127.0.0.1:5173
```

Expected edge behavior: unauthenticated requests return HTTP 302 to `parthchandak.cloudflareaccess.com/.../login/...` with `www-authenticate: Cloudflare-Access`.
