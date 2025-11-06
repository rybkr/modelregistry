#!/bin/bash
# AWS Setup Script for Model Registry
# This script helps set up AWS infrastructure for the Model Registry

set -e  # Exit on error

echo "🚀 Model Registry AWS Setup"
echo "============================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    echo "Install it with: brew install awscli (macOS) or pip install awscli"
    exit 1
fi

echo -e "${GREEN}✅ AWS CLI found${NC}"

# Check if AWS credentials are configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${YELLOW}⚠️  AWS credentials not configured${NC}"
    echo "Running: aws configure"
    aws configure
fi

echo -e "${GREEN}✅ AWS credentials configured${NC}"

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Account ID: $ACCOUNT_ID"

# Check if EB CLI is installed
if ! command -v eb &> /dev/null; then
    echo -e "${YELLOW}⚠️  Elastic Beanstalk CLI not installed${NC}"
    echo "Installing..."
    pip install awsebcli
fi

echo -e "${GREEN}✅ Elastic Beanstalk CLI found${NC}"

# Check if IAM user exists
if ! aws iam get-user --user-name github-actions-deployer &> /dev/null; then
    echo -e "${YELLOW}⚠️  IAM user 'github-actions-deployer' does not exist${NC}"
    echo "Creating IAM user..."
    
    aws iam create-user --user-name github-actions-deployer
    
    # Create access key
    echo "Creating access key..."
    OUTPUT=$(aws iam create-access-key --user-name github-actions-deployer)
    
    echo ""
    echo -e "${GREEN}✅ IAM user created!${NC}"
    echo ""
    echo -e "${YELLOW}📝 IMPORTANT: Add these to GitHub Secrets:${NC}"
    echo "$OUTPUT" | python3 -c "import sys, json; data = json.load(sys.stdin); ak = data['AccessKey']; print(f'AWS_ACCESS_KEY_ID: {ak[\"AccessKeyId\"]}'); print(f'AWS_SECRET_ACCESS_KEY: {ak[\"SecretAccessKey\"]}')"
    echo ""
    
    # Attach policies
    echo "Attaching IAM policies..."
    aws iam attach-user-policy \
      --user-name github-actions-deployer \
      --policy-arn arn:aws:iam::aws:policy/AWSElasticBeanstalkFullAccess
    
    aws iam attach-user-policy \
      --user-name github-actions-deployer \
      --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
    
    aws iam attach-user-policy \
      --user-name github-actions-deployer \
      --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
    
    echo -e "${GREEN}✅ Policies attached${NC}"
    
    # Add custom inline policy for S3 bucket ownership controls (required for EB)
    echo "Adding S3 bucket ownership controls permission..."
    aws iam put-user-policy \
      --user-name github-actions-deployer \
      --policy-name EBDeploymentS3Permissions \
      --policy-document '{
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
    
    echo -e "${GREEN}✅ S3 ownership controls permission added${NC}"
else
    echo -e "${GREEN}✅ IAM user 'github-actions-deployer' exists${NC}"
    
    # Ensure the S3 ownership controls permission is added even if user already exists
    echo "Checking S3 bucket ownership controls permission..."
    if ! aws iam get-user-policy --user-name github-actions-deployer --policy-name EBDeploymentS3Permissions &> /dev/null; then
        echo "Adding S3 bucket ownership controls permission..."
        aws iam put-user-policy \
          --user-name github-actions-deployer \
          --policy-name EBDeploymentS3Permissions \
          --policy-document '{
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
        echo -e "${GREEN}✅ S3 ownership controls permission added${NC}"
    else
        echo -e "${GREEN}✅ S3 ownership controls permission already exists${NC}"
    fi
fi

# Initialize Elastic Beanstalk if not already done
if [ ! -f ".elasticbeanstalk/config.yml" ]; then
    echo -e "${YELLOW}⚠️  Elastic Beanstalk not initialized${NC}"
    echo "Initializing..."
    
    # Non-interactive init
    eb init model-registry \
      --region us-east-1 \
      --platform "Python 3.11" \
      --non-interactive || true
    
    echo -e "${GREEN}✅ Elastic Beanstalk initialized${NC}"
else
    echo -e "${GREEN}✅ Elastic Beanstalk already initialized${NC}"
fi

echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Add AWS secrets to GitHub (Settings → Secrets → Actions)"
echo "2. Run: eb create model-registry-production"
echo "3. Or push to main branch and GitHub Actions will deploy automatically"
echo ""
echo "For detailed instructions, see: AWS_DEPLOYMENT_GUIDE.md"



