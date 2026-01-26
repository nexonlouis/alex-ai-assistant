#!/bin/bash
# Alex AI Assistant - GCP Setup Script
# Run this script to configure GCP for deployment

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="us-central1"
SERVICE_NAME="alex-api"
REPO_NAME="alex-repo"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Alex AI Assistant - GCP Setup ===${NC}"

# Check if PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}GCP_PROJECT_ID not set. Attempting to get from gcloud...${NC}"
    PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}Error: No GCP project configured.${NC}"
        echo "Set GCP_PROJECT_ID environment variable or run: gcloud config set project YOUR_PROJECT_ID"
        exit 1
    fi
fi

echo -e "${GREEN}Using project: ${PROJECT_ID}${NC}"

# Enable required APIs
echo -e "\n${YELLOW}Enabling required APIs...${NC}"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    --project="$PROJECT_ID"

echo -e "${GREEN}APIs enabled successfully${NC}"

# Create Artifact Registry repository
echo -e "\n${YELLOW}Creating Artifact Registry repository...${NC}"
gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Alex AI Assistant container images" \
    --project="$PROJECT_ID" 2>/dev/null || echo "Repository already exists"

echo -e "${GREEN}Artifact Registry configured${NC}"

# Function to create or update a secret
create_secret() {
    local secret_name=$1
    local secret_value=$2

    # Check if secret exists
    if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" &>/dev/null; then
        echo "Updating secret: $secret_name"
        echo -n "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=- --project="$PROJECT_ID"
    else
        echo "Creating secret: $secret_name"
        echo -n "$secret_value" | gcloud secrets create "$secret_name" --data-file=- --project="$PROJECT_ID"
    fi
}

# Setup secrets
echo -e "\n${YELLOW}Setting up secrets in Secret Manager...${NC}"
echo "You will be prompted for each secret value."
echo ""

# GOOGLE_API_KEY
read -p "Enter GOOGLE_API_KEY (Gemini API key): " -s GOOGLE_API_KEY
echo ""
if [ -n "$GOOGLE_API_KEY" ]; then
    create_secret "GOOGLE_API_KEY" "$GOOGLE_API_KEY"
fi

# NEO4J_URI
read -p "Enter NEO4J_URI (e.g., neo4j+s://xxx.databases.neo4j.io): " NEO4J_URI
if [ -n "$NEO4J_URI" ]; then
    create_secret "NEO4J_URI" "$NEO4J_URI"
fi

# NEO4J_USERNAME
read -p "Enter NEO4J_USERNAME [neo4j]: " NEO4J_USERNAME
NEO4J_USERNAME=${NEO4J_USERNAME:-neo4j}
create_secret "NEO4J_USERNAME" "$NEO4J_USERNAME"

# NEO4J_PASSWORD
read -p "Enter NEO4J_PASSWORD: " -s NEO4J_PASSWORD
echo ""
if [ -n "$NEO4J_PASSWORD" ]; then
    create_secret "NEO4J_PASSWORD" "$NEO4J_PASSWORD"
fi

# ANTHROPIC_API_KEY (optional)
read -p "Enter ANTHROPIC_API_KEY (optional, for Claude Code): " -s ANTHROPIC_API_KEY
echo ""
if [ -n "$ANTHROPIC_API_KEY" ]; then
    create_secret "ANTHROPIC_API_KEY" "$ANTHROPIC_API_KEY"
fi

echo -e "${GREEN}Secrets configured${NC}"

# Grant Cloud Run access to secrets
echo -e "\n${YELLOW}Granting Cloud Run access to secrets...${NC}"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
CLOUD_RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in GOOGLE_API_KEY NEO4J_URI NEO4J_USERNAME NEO4J_PASSWORD; do
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:${CLOUD_RUN_SA}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$PROJECT_ID" 2>/dev/null || true
done

# Add ANTHROPIC_API_KEY if it exists
if gcloud secrets describe "ANTHROPIC_API_KEY" --project="$PROJECT_ID" &>/dev/null; then
    gcloud secrets add-iam-policy-binding "ANTHROPIC_API_KEY" \
        --member="serviceAccount:${CLOUD_RUN_SA}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$PROJECT_ID" 2>/dev/null || true
fi

echo -e "${GREEN}Permissions configured${NC}"

# Summary
echo -e "\n${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Deploy manually:    gcloud run deploy $SERVICE_NAME --source . --region $REGION"
echo "2. Or trigger build:   gcloud builds submit --config cloudbuild.yaml"
echo ""
echo "Useful commands:"
echo "  View logs:    gcloud run logs read --service $SERVICE_NAME --region $REGION"
echo "  Get URL:      gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)'"
