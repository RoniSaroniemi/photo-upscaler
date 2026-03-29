# Acting CEO — Stage-Gated Notes (Honest Image Tools)

*Information held by the acting CEO for delivery to the CPO at the right lifecycle stage. The CPO does NOT read this file — the acting CEO releases relevant sections when the project advances to that stage.*

---

## POC Stage Notes
*Release to CPO: at project start — RELEASED*

- Core uncertainty: Can Real-ESRGAN run on Cloud Run at viable cost?
- Competitive landscape: no competitor shows cost breakdown — transparency is genuinely novel
- Pricing model: prepaid balance in real currency, $5 min top-up via Stripe

---

## Architecture Stage Notes
*Release to CPO: when CEO approves POC gate → Architecture*

- Two-container architecture: Next.js (frontend + API) + Python/FastAPI (inference worker)
- GCP project: `photo-upscaler-24h` (billing linked, Cloud Run + Artifact Registry + Cloud Build enabled)
- Region: consider `europe-north1` (same as CEO's work project) vs `us-central1` (where POC deployed)

---

## Alpha Stage Notes
*Release to CPO: when CEO approves Architecture gate → Alpha*

- Core flow only: upload → upscale → download
- No auth, no payments — just the pipeline working end-to-end
- Use `/verify` skill to confirm the flow works (Playwright screenshots)

---

## Beta Stage Notes
*Release to CPO: when CEO approves Alpha gate → Beta*

- **GCP infrastructure reference:** `/Users/roni-saroniemi/Github/foxie-reporting` — benchmark for Cloud SQL, storage buckets, service accounts, IAM patterns. The foxie-reporting project uses the same GCP organization (foxie.ai) and has proven patterns for Cloud Run + Cloud SQL integration.
- Auth: email magic link (simple, passwordless)
- Payments: Stripe prepaid balance, $5 min top-up, show cost breakdown per image
- UI: ~80% visual fidelity, before/after comparison slider, transparent pricing display
- Developer greeting + "buy me a coffee" option

---

## Production Stage Notes
*Release to CPO: when CEO approves Beta gate → Production*

- Full security audit before go-live
- Live Stripe (not sandbox)
- Performance: cold start is acceptable, optimize inference time if bottleneck
- Privacy: images deleted within 1 hour, document this for users
- Domain setup (Cloudflare available if needed)

---
