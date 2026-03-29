#!/usr/bin/env bash
set -euo pipefail

# Honest Image Tools — Deployment Script
# Usage: ./scripts/deploy.sh [staging|production]

ENVIRONMENT="${1:-}"
PROJECT_ID="photo-upscaler-24h"
REGION="us-central1"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/images"
GCS_BUCKET="honest-image-uploads"

if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
  echo "Usage: ./scripts/deploy.sh [staging|production]"
  echo "  staging    — deploy to staging Cloud Run services"
  echo "  production — deploy to production Cloud Run services"
  exit 1
fi

SUFFIX="$ENVIRONMENT"
SHORT_SHA=$(git rev-parse --short HEAD)
TAG="${SHORT_SHA}"

echo "=== Deploying to ${ENVIRONMENT} (tag: ${TAG}) ==="

# ── Build Docker images ──────────────────────────────────────────────
echo "Building inference image..."
docker build -t "${REGISTRY}/inference:${TAG}" -t "${REGISTRY}/inference:latest" ./inference

echo "Building frontend image..."
docker build -t "${REGISTRY}/frontend:${TAG}" -t "${REGISTRY}/frontend:latest" ./frontend

# ── Push to Artifact Registry ────────────────────────────────────────
echo "Pushing inference image..."
docker push "${REGISTRY}/inference:${TAG}"
docker push "${REGISTRY}/inference:latest"

echo "Pushing frontend image..."
docker push "${REGISTRY}/frontend:${TAG}"
docker push "${REGISTRY}/frontend:latest"

# ── Deploy inference to Cloud Run ────────────────────────────────────
echo "Deploying inference service..."
gcloud run deploy "inference-${SUFFIX}" \
  --image "${REGISTRY}/inference:${TAG}" \
  --region "${REGION}" \
  --cpu 4 \
  --memory 8Gi \
  --concurrency 1 \
  --timeout 120 \
  --min-instances 0 \
  --max-instances 5 \
  --no-allow-unauthenticated \
  --project "${PROJECT_ID}"

INFERENCE_URL=$(gcloud run services describe "inference-${SUFFIX}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(status.url)')

# ── Deploy frontend to Cloud Run ─────────────────────────────────────
echo "Deploying frontend service..."
gcloud run deploy "frontend-${SUFFIX}" \
  --image "${REGISTRY}/frontend:${TAG}" \
  --region "${REGION}" \
  --cpu 1 \
  --memory 512Mi \
  --concurrency 80 \
  --timeout 120 \
  --min-instances 0 \
  --max-instances 3 \
  --allow-unauthenticated \
  --set-env-vars "NODE_ENV=production,INFERENCE_SERVICE_URL=${INFERENCE_URL}" \
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_PUBLISHABLE_KEY=STRIPE_PUBLISHABLE_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,EMAIL_FROM=EMAIL_FROM:latest,EMAIL_APP_PASSWORD=EMAIL_APP_PASSWORD:latest,JWT_SECRET=JWT_SECRET:latest,GCS_BUCKET_NAME=GCS_BUCKET_NAME:latest,NEXT_PUBLIC_BASE_URL=NEXT_PUBLIC_BASE_URL:latest" \
  --project "${PROJECT_ID}"

FRONTEND_URL=$(gcloud run services describe "frontend-${SUFFIX}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(status.url)')

# ── Health checks ────────────────────────────────────────────────────
echo "Running health checks..."

echo -n "Frontend health: "
if curl -sf "${FRONTEND_URL}/api/health" > /dev/null 2>&1; then
  echo "OK"
else
  echo "FAILED"
  exit 1
fi

echo -n "Inference reachable: "
if curl -sf -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${INFERENCE_URL}/health" > /dev/null 2>&1; then
  echo "OK"
else
  echo "FAILED (may need IAM setup)"
fi

# ── IAM: frontend SA can invoke inference ────────────────────────────
echo "Setting up IAM..."
FRONTEND_SA=$(gcloud run services describe "frontend-${SUFFIX}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(spec.template.spec.serviceAccountName)')

if [[ -n "$FRONTEND_SA" ]]; then
  gcloud run services add-iam-policy-binding "inference-${SUFFIX}" \
    --region "${REGION}" \
    --member "serviceAccount:${FRONTEND_SA}" \
    --role "roles/run.invoker" \
    --project "${PROJECT_ID}" \
    --quiet
  echo "IAM: ${FRONTEND_SA} -> roles/run.invoker on inference-${SUFFIX}"
fi

# ── GCS bucket with 24h lifecycle ────────────────────────────────────
echo "Ensuring GCS bucket exists..."
if ! gsutil ls "gs://${GCS_BUCKET}" > /dev/null 2>&1; then
  gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${GCS_BUCKET}"
  echo "Created bucket gs://${GCS_BUCKET}"
fi

echo "Applying 24h lifecycle policy..."
gsutil lifecycle set config/gcs-lifecycle.json "gs://${GCS_BUCKET}"

echo ""
echo "=== Deployment complete ==="
echo "Frontend: ${FRONTEND_URL}"
echo "Inference: ${INFERENCE_URL}"
