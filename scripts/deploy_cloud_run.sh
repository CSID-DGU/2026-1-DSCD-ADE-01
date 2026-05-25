#!/usr/bin/env bash
set -Eeuo pipefail

REGION="us-central1"
SERVICE_NAME="ade-contract-api"
REPOSITORY="ade-api"
IMAGE_NAME="ade-contract-api"
ENV_FILE=".env"
ALLOW_UNAUTHENTICATED="true"
RUN_TESTS="true"
TAG=""
PROJECT_ID="${PROJECT_ID:-}"

usage() {
  cat <<'EOF'
Deploy the ADE FastAPI service to Cloud Run.

Usage:
  PROJECT_ID=your-project ./scripts/deploy_cloud_run.sh [options]

Options:
  --project-id VALUE       GCP project ID. Defaults to PROJECT_ID env or GCP_PROJECT_ID in .env.
  --region VALUE           GCP region. Default: us-central1.
  --service VALUE          Cloud Run service name. Default: ade-contract-api.
  --repo VALUE             Artifact Registry repository. Default: ade-api.
  --image-name VALUE       Docker image name. Default: ade-contract-api.
  --env-file VALUE         Environment file for Cloud Run. Default: .env.
  --tag VALUE              Image tag. Default: YYYYMMDD-HHMMSS-gitsha.
  --private                Do not allow unauthenticated access.
  --skip-tests             Skip local pytest check before build.
  -h, --help               Show this help.

Examples:
  PROJECT_ID=my-project ./scripts/deploy_cloud_run.sh
  ./scripts/deploy_cloud_run.sh --project-id my-project --private
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

read_env_value() {
  local key="$1"
  local file="$2"

  awk -F= -v key="$key" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      gsub(/^"|"$/, "", value)
      gsub(/^'\''|'\''$/, "", value)
      print value
      exit
    }
  ' "$file"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID="${2:-}"
      shift 2
      ;;
    --region)
      REGION="${2:-}"
      shift 2
      ;;
    --service)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --repo)
      REPOSITORY="${2:-}"
      shift 2
      ;;
    --image-name)
      IMAGE_NAME="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --tag)
      TAG="${2:-}"
      shift 2
      ;;
    --private)
      ALLOW_UNAUTHENTICATED="false"
      shift
      ;;
    --skip-tests)
      RUN_TESTS="false"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

require_command gcloud
require_command curl

[[ -f "$ENV_FILE" ]] || die "Environment file not found: $ENV_FILE"

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(read_env_value GCP_PROJECT_ID "$ENV_FILE")"
fi
[[ -n "$PROJECT_ID" ]] || die "PROJECT_ID is required. Pass --project-id or set GCP_PROJECT_ID in $ENV_FILE."

if [[ -z "$TAG" ]]; then
  timestamp="$(date +%Y%m%d-%H%M%S)"
  git_sha="$(git rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -n "$git_sha" ]]; then
    TAG="${timestamp}-${git_sha}"
  else
    TAG="$timestamp"
  fi
fi

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${TAG}"

echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo "Service:  $SERVICE_NAME"
echo "Image:    $IMAGE"
echo "Env file: $ENV_FILE"

gcloud config set project "$PROJECT_ID" >/dev/null

echo "Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  documentai.googleapis.com \
  aiplatform.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com

echo "Ensuring Artifact Registry repository exists..."
if ! gcloud artifacts repositories describe "$REPOSITORY" --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="ADE API Docker images"
fi

if [[ "$RUN_TESTS" == "true" ]]; then
  require_command pytest
  echo "Running local API tests..."
  pytest tests/app/test_main.py -q
fi

echo "Building and pushing image via Cloud Build (GCP 내부 빌드)..."
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions "_IMAGE=${IMAGE}" \
  .

deploy_args=(
  run deploy "$SERVICE_NAME"
  --image "$IMAGE"
  --region "$REGION"
  --env-vars-file "$ENV_FILE"
  --memory 4Gi
  --cpu 2
  --min-instances 1
  --timeout 300
)

if [[ "$ALLOW_UNAUTHENTICATED" == "true" ]]; then
  deploy_args+=(--allow-unauthenticated)
else
  deploy_args+=(--no-allow-unauthenticated)
fi

echo "Deploying to Cloud Run..."
gcloud "${deploy_args[@]}"

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')"
echo "Service URL: $SERVICE_URL"

echo "Checking /health..."
if [[ "$ALLOW_UNAUTHENTICATED" == "true" ]]; then
  curl -fsS "$SERVICE_URL/health"
else
  IDENTITY_TOKEN="$(gcloud auth print-identity-token)"
  curl -fsS -H "Authorization: Bearer ${IDENTITY_TOKEN}" "$SERVICE_URL/health"
fi
echo
