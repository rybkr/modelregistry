#!/bin/bash
# Fix IAM Permissions for Elastic Beanstalk Deployment
# This script adds the missing S3 permission for EB deployment

set -e

echo "🔧 Fixing IAM Permissions for Elastic Beanstalk"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

USER_NAME="github-actions-deployer"
POLICY_NAME="EBDeploymentS3Permissions"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    exit 1
fi

# Check if user exists
if ! aws iam get-user --user-name "$USER_NAME" &> /dev/null; then
    echo -e "${RED}❌ IAM user '$USER_NAME' does not exist${NC}"
    echo "Run ./scripts/aws_setup.sh first to create the user"
    exit 1
fi

echo -e "${GREEN}✅ IAM user '$USER_NAME' found${NC}"

# Add inline policy directly to user (simpler than managed policy)
echo "Adding S3 bucket ownership controls permission as inline policy..."

POLICY_DOCUMENT='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutBucketOwnershipControls",
        "s3:GetBucketOwnershipControls",
        "s3:DeleteBucketOwnershipControls"
      ],
      "Resource": "arn:aws:s3:::elasticbeanstalk-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutBucketOwnershipControls",
        "s3:GetBucketOwnershipControls",
        "s3:DeleteBucketOwnershipControls"
      ],
      "Resource": "arn:aws:s3:::elasticbeanstalk-*/*"
    }
  ]
}'

# Check if inline policy already exists
if aws iam get-user-policy --user-name "$USER_NAME" --policy-name "$POLICY_NAME" &> /dev/null; then
    echo -e "${YELLOW}⚠️  Inline policy '$POLICY_NAME' already exists, updating...${NC}"
    aws iam put-user-policy \
        --user-name "$USER_NAME" \
        --policy-name "$POLICY_NAME" \
        --policy-document "$POLICY_DOCUMENT"
    echo -e "${GREEN}✅ Policy updated${NC}"
else
    echo "Creating new inline policy..."
    aws iam put-user-policy \
        --user-name "$USER_NAME" \
        --policy-name "$POLICY_NAME" \
        --policy-document "$POLICY_DOCUMENT"
    echo -e "${GREEN}✅ Policy created and attached${NC}"
fi

echo ""
echo -e "${GREEN}✅ Permissions fixed!${NC}"
echo ""
echo "The IAM user now has the necessary S3 permissions for Elastic Beanstalk."
echo "You can now retry the deployment."

