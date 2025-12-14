#!/bin/bash
set -e

#BUCKET_NAME="model-registry-users-$(date +%s)"
BUCKET_NAME="model-registry-packages-$(date +%s)"
REGION="us-east-1"

echo "Creating S3 bucket: $BUCKET_NAME"
aws s3 mb s3://$BUCKET_NAME --region $REGION
aws s3api put-object --bucket $BUCKET_NAME --key users/ --region $REGION

echo ""
echo "[+] S3 bucket created: $BUCKET_NAME"
echo ""
echo "Next steps:"
echo "1. Generate password hash:"
echo "   python3 -c 'from src.auth import hash_password; print(hash_password(\"your-password\"))'"
echo ""
echo "2. Set EB environment variables:"
#echo "   eb setenv USER_STORAGE_BUCKET=$BUCKET_NAME DEFAULT_ADMIN_PASSWORD_HASH=<your-hash>"
echo "   eb setenv PACKAGE_STORAGE_BUCKET=$BUCKET_NAME DEFAULT_ADMIN_PASSWORD_HASH=<your-hash>"
echo ""
echo "3. Attach IAM policy to EB instance role (see guide above)"
