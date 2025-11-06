# Fix IAM Permissions for Elastic Beanstalk Deployment

## Problem

When deploying to Elastic Beanstalk, you may encounter this error:

```
ERROR: NotAuthorizedError - Operation Denied. User: arn:aws:iam::ACCOUNT:user/github-actions-deployer 
is not authorized to perform: s3:PutBucketOwnershipControls on resource: 
"arn:aws:s3:::elasticbeanstalk-***-ACCOUNT" because no identity-based policy 
allows the s3:PutBucketOwnershipControls action
```

## Solution

The IAM user needs additional S3 permissions for bucket ownership controls. You can fix this in two ways:

### Option 1: Run the Fix Script (Recommended)

```bash
./scripts/fix_iam_permissions.sh
```

This script will automatically add the missing permissions to your IAM user.

### Option 2: Manual Fix via AWS Console

1. Go to AWS Console → IAM → Users → `github-actions-deployer`
2. Click on "Add permissions" → "Create inline policy"
3. Use the JSON editor and paste this policy:

```json
{
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
}
```

4. Name it `EBDeploymentS3Permissions` and save

### Option 3: Manual Fix via AWS CLI

```bash
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
```

## Why This Happens

Elastic Beanstalk needs to create and manage S3 buckets for storing application versions. The `s3:PutBucketOwnershipControls` permission is required to set bucket ownership controls, which is a newer S3 feature that helps ensure proper access control.

## After Fixing

Once you've added the permissions, retry your deployment:

1. If using GitHub Actions, push a new commit or re-run the workflow
2. If deploying manually, run `eb create` or `eb deploy` again

The deployment should now proceed without this permission error.

