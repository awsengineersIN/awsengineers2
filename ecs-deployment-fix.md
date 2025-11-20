# ECS Deployment Fix Guide

## Problem
Getting error: `InvalidConfiguration - The config profile (default) could not be found`

This happens because ECS containers should use **IAM Task Roles**, not AWS profiles.

---

## Solution Steps

### Step 1: Update Your Code

Replace `modules/config.py` with the updated version (see config-ecs-updated.md file).

**Key changes:**
- Detects if running in ECS automatically
- Uses Task IAM Role in ECS (no profile needed)
- Falls back to profile for local development

---

### Step 2: Create/Update ECS Task IAM Role

Your ECS task needs an IAM role with these permissions:

#### A. Task Role Policy (for Management Account Operations)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "organizations:ListAccounts",
        "organizations:DescribeOrganization",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/ReadOnlyRole"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeRegions",
        "ec2:DescribeInstances"
      ],
      "Resource": "*"
    }
  ]
}
```

#### B. Trust Relationship for Task Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

---

### Step 3: Update ECS Task Definition

In your ECS task definition, specify the **Task Role** (not Execution Role):

```json
{
  "family": "aws-dashboard",
  "taskRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/YourTaskRole",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "streamlit-dashboard",
      "image": "YOUR_ECR_IMAGE",
      "portMappings": [
        {
          "containerPort": 8501,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "READONLY_ROLE_NAME",
          "value": "ReadOnlyRole"
        },
        {
          "name": "MAX_WORKERS",
          "value": "10"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/aws-dashboard",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024"
}
```

**Important:** 
- `taskRoleArn` = IAM role with AWS service permissions (Organizations, STS, EC2, etc.)
- `executionRoleArn` = IAM role for ECS to pull images and write logs

---

### Step 4: Remove AWS Profile Environment Variables

**Remove these from your ECS task definition** (if present):
```bash
# ❌ Don't set these in ECS
AWS_PROFILE=default
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

**Only keep these:**
```bash
# ✅ Keep these configuration variables
READONLY_ROLE_NAME=ReadOnlyRole
MAX_WORKERS=10
```

---

### Step 5: Deploy Updated Code

1. **Build new Docker image** with updated `modules/config.py`
   ```bash
   docker build -t aws-dashboard:latest .
   ```

2. **Push to ECR**
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
   
   docker tag aws-dashboard:latest YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/aws-dashboard:latest
   
   docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/aws-dashboard:latest
   ```

3. **Update ECS service** to use new task definition

4. **Restart tasks**
   ```bash
   aws ecs update-service \
     --cluster your-cluster \
     --service aws-dashboard \
     --force-new-deployment
   ```

---

## Verification

After deployment, check CloudWatch Logs for:

```
🐳 Running in ECS - Using Task IAM Role
✅ ECS Task Role authenticated successfully (Account: 123456789012)
✅ Found N active account(s)
```

If you see this, it's working correctly!

---

## Troubleshooting

### Error: "Access Denied"
- **Cause:** Task IAM role doesn't have required permissions
- **Fix:** Add Organizations, STS, EC2 permissions to task role

### Error: "Could not assume role"
- **Cause:** ReadOnlyRole in member accounts doesn't trust your management account
- **Fix:** Update trust policy in member account roles:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "AWS": "arn:aws:iam::MANAGEMENT_ACCOUNT_ID:root"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }
  ```

### Still seeing profile error
- **Cause:** Old container image still running
- **Fix:** Force new deployment and verify image tag

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│         ECS Task (Fargate)              │
│  ┌───────────────────────────────────┐  │
│  │   Streamlit Dashboard Container   │  │
│  │                                   │  │
│  │   Uses Task IAM Role              │  │
│  │   (Automatically via boto3)       │  │
│  └───────────────────────────────────┘  │
│              ↓                           │
│    ┌──────────────────┐                 │
│    │   Task IAM Role  │                 │
│    └──────────────────┘                 │
└─────────────────────────────────────────┘
              ↓
    ┌──────────────────────┐
    │  AWS Organizations   │
    │  List Accounts       │
    └──────────────────────┘
              ↓
    ┌──────────────────────┐
    │ Member Account Roles │
    │ (via STS AssumeRole) │
    └──────────────────────┘
              ↓
    ┌──────────────────────┐
    │   EC2, SecurityHub,  │
    │   Config, IAM APIs   │
    └──────────────────────┘
```

---

## Summary

**The key fix:** Update `modules/config.py` to detect ECS environment and use Task IAM Role instead of AWS profiles.

**Benefits of this approach:**
- ✅ No credentials in environment variables
- ✅ Automatic credential rotation (AWS manages it)
- ✅ Works in both ECS and local development
- ✅ Follows AWS security best practices
- ✅ Single codebase for all environments
