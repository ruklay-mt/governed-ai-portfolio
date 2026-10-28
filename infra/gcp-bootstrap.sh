#!/usr/bin/env bash
# One-off Google Cloud setup for deploying the API from GitHub Actions (ADR 0002).
# Safe to re-run: every step skips resources that already exist.
# No service-account keys are created; GitHub authenticates with Workload Identity Federation.
#
# Usage: infra/gcp-bootstrap.sh <project-id> <github-owner/repo>
set -euo pipefail

PROJECT_ID=${1:?project id}
REPO=${2:?github owner/repo}
REGION=australia-southeast1
AR_REPO=portfolio
# Runtime secrets (values are added by the owner, never by this script). DATABASE_URL holds
# only host + database: the API connects as persona logins and app_service (ADR 0013).
SECRETS=(
  database-url
  agent-db-password-sales-rep-nz-south
  agent-db-password-sales-manager
  agent-db-password-finance
  agent-db-password-support
  app-service-db-password
  anthropic-api-key
  voyage-api-key
  langfuse-secret-key
)
RUNTIME_SA=api-runtime@${PROJECT_ID}.iam.gserviceaccount.com
DEPLOYER_SA=github-deployer@${PROJECT_ID}.iam.gserviceaccount.com
POOL=github
PROVIDER=github-oidc

gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format 'value(projectNumber)')

echo "Enabling APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

echo "Artifact Registry"
gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$AR_REPO" --repository-format docker --location "$REGION"

echo "Service accounts"
gcloud iam service-accounts describe "$RUNTIME_SA" >/dev/null 2>&1 ||
  gcloud iam service-accounts create api-runtime --display-name "Cloud Run runtime for the API"
gcloud iam service-accounts describe "$DEPLOYER_SA" >/dev/null 2>&1 ||
  gcloud iam service-accounts create github-deployer --display-name "GitHub Actions deployer"

echo "Secrets (values are added separately by the owner)"
for secret in "${SECRETS[@]}"; do
  gcloud secrets describe "$secret" >/dev/null 2>&1 ||
    gcloud secrets create "$secret" --replication-policy automatic
  gcloud secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:$RUNTIME_SA" --role roles/secretmanager.secretAccessor >/dev/null
done

echo "Deployer permissions"
for role in roles/run.admin roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:$DEPLOYER_SA" --role "$role" --condition None >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member "serviceAccount:$DEPLOYER_SA" --role roles/iam.serviceAccountUser >/dev/null

echo "Workload Identity Federation (only $REPO may use it)"
gcloud iam workload-identity-pools describe "$POOL" --location global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" --location global --display-name "GitHub Actions"
gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --location global --workload-identity-pool "$POOL" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --location global --workload-identity-pool "$POOL" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition "assertion.repository == '$REPO'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$REPO" \
  >/dev/null

echo
echo "GitHub repository variables (not secrets):"
echo "  GCP_PROJECT_ID=$PROJECT_ID"
echo "  GCP_REGION=$REGION"
echo "  GCP_WIF_PROVIDER=projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
echo "  GCP_DEPLOYER_SA=$DEPLOYER_SA"
echo "  GCP_RUNTIME_SA=$RUNTIME_SA"
