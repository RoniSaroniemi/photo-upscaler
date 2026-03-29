# Brief — Deployment + CI/CD + E2E Testing

**Scope:** Set up Cloud Build CI/CD, deploy both services to Cloud Run, configure service-to-service IAM, and create E2E test suite.
**Branch:** `feature/deployment` — new worktree
**Effort estimate:** L (~2 hours)
**Risk:** Medium (IAM configuration, multi-service deployment coordination)
**Affects:** `cloudbuild.yaml`, `Dockerfile` (frontend), deployment scripts, Playwright test suite, GCS lifecycle config
**Project:** PRJ-001 (Honest Image Tools Beta)

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] All prior briefs (1-6) merged to main
- [ ] Docker: `docker --version`
- [ ] gcloud CLI: `gcloud --version`
- [ ] Playwright: `npx playwright --version`

### Credentials & Access
- [ ] GCP project `photo-upscaler-24h` with billing enabled
- [ ] Cloud Build API enabled (confirmed)
- [ ] Cloud Run API enabled (confirmed)
- [ ] Artifact Registry API enabled (confirmed)
- [ ] GitHub repo connected to Cloud Build (or use manual triggers)

### Verification Capability
- [ ] Can verify via: deployed URLs return 200 on health endpoints
- [ ] Can verify via: Playwright E2E tests against deployed staging
- [ ] Can verify via: `/verify` skill for comprehensive check

### Human Dependencies
- [ ] Domain name + DNS configuration — **optional for Beta** (Cloud Run URLs work fine)
- [ ] Production environment variables — same as dev but with live Stripe keys (deferred to Production stage)

---

## 1. The Problem (Why)

The application is built but only runs locally. It needs to be deployed to Cloud Run with proper CI/CD, service-to-service authentication, and automated testing to validate the full stack works in a cloud environment.

---

## 2. The Solution (What)

### 2.1 Frontend Dockerfile

Create `frontend/Dockerfile`:
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

Next.js standalone output mode (`output: "standalone"` in `next.config.ts`).

### 2.2 Cloud Build Configuration

Create `cloudbuild.yaml` for automated builds:

**Triggers:**
- Push to `main` branch → build + deploy to staging
- Manual trigger → deploy to production (future)

**Steps:**
1. Build inference Docker image → push to Artifact Registry
2. Build frontend Docker image → push to Artifact Registry
3. Deploy inference to Cloud Run (staging)
4. Deploy frontend to Cloud Run (staging)
5. Run health checks against staging URLs
6. (Optional) Run Playwright E2E against staging

### 2.3 Cloud Run Deployment

**Inference service:** `inference-staging`
```bash
gcloud run deploy inference-staging \
  --image us-central1-docker.pkg.dev/photo-upscaler-24h/images/inference:latest \
  --platform managed \
  --region us-central1 \
  --cpu 4 --memory 8Gi \
  --concurrency 1 \
  --timeout 120 \
  --min-instances 0 --max-instances 5 \
  --no-allow-unauthenticated
```

**Frontend service:** `frontend-staging`
```bash
gcloud run deploy frontend-staging \
  --image us-central1-docker.pkg.dev/photo-upscaler-24h/images/frontend:latest \
  --platform managed \
  --region us-central1 \
  --cpu 1 --memory 512Mi \
  --concurrency 80 \
  --timeout 120 \
  --min-instances 0 --max-instances 3 \
  --allow-unauthenticated \
  --set-env-vars "INFERENCE_SERVICE_URL=https://inference-staging-xxx.run.app" \
  --set-env-vars "NODE_ENV=production"
```

**Environment variables** for frontend (set via `--set-env-vars` or Secret Manager):
- `DATABASE_URL` — Neon connection string
- `INFERENCE_SERVICE_URL` — inference Cloud Run URL
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
- `EMAIL_FROM`, `EMAIL_APP_PASSWORD`
- `JWT_SECRET`
- `GCS_BUCKET_NAME`
- `NEXT_PUBLIC_BASE_URL` — frontend URL for magic link generation

### 2.4 Service-to-Service IAM

The frontend service account needs permission to invoke the inference service:

```bash
# Get the frontend service's default service account
FRONTEND_SA=$(gcloud run services describe frontend-staging --region us-central1 --format='value(spec.template.spec.serviceAccountName)')

# If using default compute SA:
FRONTEND_SA="132808742560-compute@developer.gserviceaccount.com"

# Grant invoker role on inference service
gcloud run services add-iam-policy-binding inference-staging \
  --region us-central1 \
  --member="serviceAccount:${FRONTEND_SA}" \
  --role="roles/run.invoker"
```

### 2.5 GCS Bucket Setup

```bash
# Create bucket (if not exists)
gsutil mb -l us-central1 -b on gs://honest-image-tools-uploads

# Set lifecycle (24h auto-delete)
cat > /tmp/lifecycle.json << 'EOF'
{
  "rule": [{
    "action": { "type": "Delete" },
    "condition": { "age": 1 }
  }]
}
EOF
gsutil lifecycle set /tmp/lifecycle.json gs://honest-image-tools-uploads

# Grant the frontend SA access to write/read
gsutil iam ch serviceAccount:${FRONTEND_SA}:objectAdmin gs://honest-image-tools-uploads
```

### 2.6 Artifact Registry Setup

```bash
# Create Docker repository (if not exists)
gcloud artifacts repositories create images \
  --repository-format=docker \
  --location=us-central1 \
  --description="Honest Image Tools container images"
```

### 2.7 E2E Test Suite (Playwright)

Create `frontend/e2e/` with Playwright tests:

**Tests:**
1. **Health check:** GET / returns 200
2. **Landing page:** renders upload area, pricing info
3. **Pricing page:** shows calculator, examples
4. **Free trial flow:** upload image → processing → completion → cost breakdown shown
5. **Auth flow:** request magic link → (verify via test helper) → logged in
6. **Add funds flow:** navigate to add funds → Stripe checkout appears
7. **Upload flow (authenticated):** upload → process → download link works
8. **Account page:** shows balance, recent transactions
9. **Mobile viewport:** all pages render at 375px width

**Playwright config:**
```typescript
{
  testDir: './e2e',
  baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
  use: {
    screenshot: 'on',
    trace: 'on-first-retry',
  },
}
```

### 2.8 Deployment Script

Create `scripts/deploy.sh` for manual deployment:
```bash
#!/bin/bash
# Usage: ./scripts/deploy.sh [staging|production]
# Builds and deploys both services to the specified environment
```

---

## 3. Design Alignment

Completes the Beta pillar for Deployment (see lifecycle.md). Uses Cloud Build for CI and Cloud Run for hosting, as specified in the architecture doc.

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** Beta

**Stage-appropriate work in this brief:**
- Staging environment deployment
- CI/CD pipeline
- E2E testing

**Out of scope for this stage:**
- Production domain + SSL + CDN
- Monitoring + alerting (Production stage)
- Auto-scaling policies beyond defaults
- Blue/green or canary deployments

---

## 4. Implementation Plan

### Phase 1: Docker + Artifact Registry
- Create frontend Dockerfile with standalone output
- Configure `next.config.ts` with `output: "standalone"`
- Create Artifact Registry repository
- Build and push both images

### Phase 2: Cloud Run Deployment
- Deploy inference service (--no-allow-unauthenticated)
- Deploy frontend service (--allow-unauthenticated)
- Set environment variables
- Configure service-to-service IAM

### Phase 3: GCS Bucket
- Create bucket with lifecycle policy
- Grant SA permissions
- Test signed URL generation from deployed service

### Phase 4: Smoke Tests
- Health check both services
- Test upload flow against deployed staging
- Verify Stripe webhook reachability

### Phase 5: E2E Tests
- Create Playwright test suite
- Run against staging
- Capture screenshots of all page states

### Phase 6: CI/CD
- Create `cloudbuild.yaml`
- Set up Cloud Build trigger on main branch
- Test: push to main → automatic build + deploy

---

## 6. Verification & Evidence

### Tests
| Test | What It Verifies |
|------|-----------------|
| Frontend health: `curl $FRONTEND_URL/api/health` → 200 | Frontend deployed |
| Inference health: authorized request to inference `/health` → 200 | Inference deployed |
| Unauthenticated request to inference → 403 | IAM auth enforced |
| Frontend can call inference (service-to-service) | IAM binding works |
| GCS upload + signed URL download | Storage pipeline works |
| Full upload flow on staging | End-to-end integration |
| Playwright E2E suite passes | All user journeys work |
| Cloud Build trigger fires on push | CI/CD works |

### Acceptance Criteria
- [ ] Both services deployed to Cloud Run staging
- [ ] Frontend is publicly accessible, inference is IAM-protected
- [ ] Service-to-service auth works (frontend can call inference)
- [ ] GCS bucket exists with 24h lifecycle
- [ ] Full upload → upscale → download flow works on staging
- [ ] Playwright E2E tests pass against staging
- [ ] Cloud Build pipeline builds and deploys on push to main
- [ ] All environment variables configured via Cloud Run env vars
- [ ] Staging URLs documented in project README

---

## 7. What This Does NOT Include

- Custom domain + SSL certificate
- CDN (Cloud CDN or Cloudflare)
- Monitoring dashboard (Grafana, Cloud Monitoring)
- Alerting (PagerDuty, email alerts)
- Log aggregation beyond Cloud Run default
- Production deployment (separate trigger, different env vars)
- Load testing
- Security scanning

---

## 8. Challenge Points

- [ ] **Next.js standalone mode:** Assume `output: "standalone"` produces a working server.js. Some Next.js features (middleware, image optimization) may behave differently in standalone mode. Test thoroughly.
- [ ] **Cloud Build permissions:** Assume the Cloud Build service account has permissions to deploy to Cloud Run and push to Artifact Registry. If not, will need IAM grants.
- [ ] **Stripe webhook URL:** The Stripe webhook needs to point to the deployed frontend URL, not localhost. Will need to update webhook endpoint in Stripe dashboard after deployment. Consider using Stripe CLI webhook forwarding for staging testing.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cloud Build quota exceeded | Builds fail | Use manual deployment as fallback |
| Service-to-service IAM misconfigured | Upload flow breaks | Test with curl + ID token before full E2E |
| Next.js standalone incompatibility | Frontend crashes | Test Docker build locally first |
| Stripe webhooks can't reach staging URL | Deposits not credited | Use Stripe CLI forwarding; add manual balance credit for testing |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin feature/deployment`
2. `gh pr create --title "PRJ-001: Cloud Run deployment + CI/CD + E2E tests" --body "..." --base main --head feature/deployment`
3. State "WORK COMPLETE — PR created, ready for review"

---

## Convention: Autonomy Bias

**Mostly autonomous.** May need human to update Stripe webhook URL in dashboard after staging deployment. Everything else is agent-executable.

---

*Brief version: 1.0 — 2026-03-29*
