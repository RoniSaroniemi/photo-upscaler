#!/usr/bin/env bash
# deploy.sh — Manual deployment script for Photo Upscaler to Google Cloud Run
#
# Usage:
#   ./scripts/deploy.sh              # deploy both services
#   ./scripts/deploy.sh backend      # deploy backend only
#   ./scripts/deploy.sh frontend     # deploy frontend only
#   ./scripts/deploy.sh setup        # one-time infra setup (Artifact Registry, APIs)

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-photo-upscaler-24h}"
REGION="${GCP_REGION:-us-central1}"
REPO="photo-upscaler"
BACKEND_SERVICE="photo-upscaler-backend"
FRONTEND_SERVICE="photo-upscaler-frontend"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
TAG="${DEPLOY_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

info()  { echo "==> $*"; }
error() { echo "ERROR: $*" >&2; exit 1; }

# ── Preflight ──
check_prereqs() {
    command -v gcloud >/dev/null 2>&1 || error "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
    command -v docker >/dev/null 2>&1 || error "docker not found"

    ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)
    if [ -z "$ACTIVE_ACCOUNT" ]; then
        error "No active gcloud account. Run: gcloud auth login"
    fi
    info "Using GCP account: ${ACTIVE_ACCOUNT}"
    info "Project: ${PROJECT_ID}, Region: ${REGION}"
}

# ── One-time setup ──
setup_infra() {
    info "Enabling required APIs..."
    gcloud services enable \
        run.googleapis.com \
        artifactregistry.googleapis.com \
        cloudbuild.googleapis.com \
        --project="${PROJECT_ID}"

    info "Creating Artifact Registry repository..."
    gcloud artifacts repositories create "${REPO}" \
        --repository-format=docker \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --description="Photo Upscaler Docker images" \
        2>/dev/null || info "Repository already exists"

    info "Configuring Docker auth for Artifact Registry..."
    gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

    info "Setup complete."
}

# ── Backend deploy ──
deploy_backend() {
    info "Building backend image..."
    docker build \
        -t "${REGISTRY}/${BACKEND_SERVICE}:${TAG}" \
        -t "${REGISTRY}/${BACKEND_SERVICE}:latest" \
        "${ROOT_DIR}/backend"

    info "Pushing backend image..."
    docker push "${REGISTRY}/${BACKEND_SERVICE}:${TAG}"
    docker push "${REGISTRY}/${BACKEND_SERVICE}:latest"

    info "Deploying backend to Cloud Run..."
    gcloud run deploy "${BACKEND_SERVICE}" \
        --image="${REGISTRY}/${BACKEND_SERVICE}:${TAG}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --platform=managed \
        --memory=4Gi \
        --cpu=4 \
        --timeout=300s \
        --concurrency=1 \
        --max-instances=5 \
        --min-instances=0 \
        --allow-unauthenticated \
        --set-env-vars="PORT=8080,TEMP_DIR=/tmp/upscaler,MODEL_NAME=RealESRGAN_x4plus,SCALE_FACTOR=4,COMPUTE_COST_PER_IMAGE=0.02,PLATFORM_FEE_PER_IMAGE=0.03"

    BACKEND_URL=$(gcloud run services describe "${BACKEND_SERVICE}" \
        --region="${REGION}" --project="${PROJECT_ID}" \
        --format='value(status.url)')
    info "Backend deployed: ${BACKEND_URL}"
    echo "${BACKEND_URL}"
}

# ── Frontend deploy ──
deploy_frontend() {
    # Get backend URL if not set
    if [ -z "${BACKEND_URL:-}" ]; then
        BACKEND_URL=$(gcloud run services describe "${BACKEND_SERVICE}" \
            --region="${REGION}" --project="${PROJECT_ID}" \
            --format='value(status.url)' 2>/dev/null || true)
    fi

    if [ -z "${BACKEND_URL:-}" ]; then
        error "Backend URL not found. Deploy backend first or set BACKEND_URL env var."
    fi

    info "Building frontend image..."
    docker build \
        -t "${REGISTRY}/${FRONTEND_SERVICE}:${TAG}" \
        -t "${REGISTRY}/${FRONTEND_SERVICE}:latest" \
        "${ROOT_DIR}/frontend"

    info "Pushing frontend image..."
    docker push "${REGISTRY}/${FRONTEND_SERVICE}:${TAG}"
    docker push "${REGISTRY}/${FRONTEND_SERVICE}:latest"

    info "Deploying frontend to Cloud Run (BACKEND_URL=${BACKEND_URL})..."
    gcloud run deploy "${FRONTEND_SERVICE}" \
        --image="${REGISTRY}/${FRONTEND_SERVICE}:${TAG}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --platform=managed \
        --memory=512Mi \
        --cpu=1 \
        --timeout=60s \
        --concurrency=80 \
        --max-instances=5 \
        --min-instances=0 \
        --allow-unauthenticated \
        --set-env-vars="NODE_ENV=production,BACKEND_URL=${BACKEND_URL}"

    FRONTEND_URL=$(gcloud run services describe "${FRONTEND_SERVICE}" \
        --region="${REGION}" --project="${PROJECT_ID}" \
        --format='value(status.url)')
    info "Frontend deployed: ${FRONTEND_URL}"

    # Update backend with frontend URL for CORS
    info "Updating backend FRONTEND_URL for CORS..."
    gcloud run services update "${BACKEND_SERVICE}" \
        --region="${REGION}" --project="${PROJECT_ID}" \
        --update-env-vars="FRONTEND_URL=${FRONTEND_URL}"

    info "Deployment complete!"
    echo ""
    echo "  Backend:  ${BACKEND_URL}"
    echo "  Frontend: ${FRONTEND_URL}"
}

# ── Main ──
check_prereqs

case "${1:-all}" in
    setup)
        setup_infra
        ;;
    backend)
        deploy_backend
        ;;
    frontend)
        deploy_frontend
        ;;
    all)
        BACKEND_URL=$(deploy_backend)
        deploy_frontend
        ;;
    *)
        echo "Usage: $0 [setup|backend|frontend|all]"
        exit 1
        ;;
esac
