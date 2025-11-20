# Updated modules/config.py with ECS Support

Save this as: `modules/config.py`

```python
"""
Configuration module for AWS credentials and settings.

Supports multiple authentication methods:
1. ECS Task Role (automatic in ECS)
2. AWS Profile (local development)
3. Environment variables (local testing)
"""

import os
import boto3
from botocore.exceptions import ClientError, ProfileNotFound

class AWSConfig:
    """Central configuration for AWS credentials and settings"""
    
    # Management account authentication
    # Priority: ECS Task Role > Environment Variables > AWS Profile
    MANAGEMENT_ACCOUNT_PROFILE = os.environ.get('AWS_PROFILE', 'default')
    
    # IAM role name to assume in member accounts
    READONLY_ROLE_NAME = os.environ.get('READONLY_ROLE_NAME', 'ReadOnlyRole')
    
    # Performance settings
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '10'))
    
    @staticmethod
    def print_config():
        """Print current configuration for debugging"""
        print("="*50)
        print("AWS Configuration")
        print("="*50)
        print(f"Profile: {AWSConfig.MANAGEMENT_ACCOUNT_PROFILE}")
        print(f"ReadOnly Role: {AWSConfig.READONLY_ROLE_NAME}")
        print(f"Max Workers: {AWSConfig.MAX_WORKERS}")
        print(f"Running in ECS: {is_running_in_ecs()}")
        print("="*50)

def is_running_in_ecs():
    """
    Detect if running in ECS by checking for ECS metadata endpoint.
    
    Returns:
        bool: True if running in ECS, False otherwise
    """
    # ECS sets these environment variables
    return (
        os.environ.get('AWS_EXECUTION_ENV', '').startswith('AWS_ECS') or
        os.environ.get('ECS_CONTAINER_METADATA_URI') is not None or
        os.environ.get('ECS_CONTAINER_METADATA_URI_V4') is not None
    )

def get_session():
    """
    Get boto3 session based on environment.
    
    For ECS: Uses IAM role attached to the task (automatic)
    For Local: Uses AWS profile or environment variables
    
    Returns:
        boto3.Session: Configured session
    """
    if is_running_in_ecs():
        # In ECS, boto3 automatically uses the task IAM role
        # No need to specify profile or credentials
        print("🐳 Running in ECS - Using Task IAM Role")
        return boto3.Session()
    else:
        # Local development - try profile first, then environment variables
        try:
            # Try using specified profile
            print(f"💻 Running locally - Attempting to use profile: {AWSConfig.MANAGEMENT_ACCOUNT_PROFILE}")
            return boto3.Session(profile_name=AWSConfig.MANAGEMENT_ACCOUNT_PROFILE)
        except ProfileNotFound:
            # Fall back to environment variables or default credentials
            print("⚠️  Profile not found - Using environment variables or default credentials")
            return boto3.Session()

def validate_aws_config():
    """
    Validate AWS configuration and credentials.
    
    Returns:
        tuple: (is_valid: bool, message: str, account_id: str)
    """
    try:
        session = get_session()
        sts_client = session.client('sts')
        
        # Get caller identity to validate credentials
        identity = sts_client.get_caller_identity()
        account_id = identity['Account']
        user_arn = identity['Arn']
        
        if is_running_in_ecs():
            message = f"✅ ECS Task Role authenticated successfully (Account: {account_id})"
        else:
            message = f"✅ AWS credentials validated (Account: {account_id})"
        
        return True, message, account_id
        
    except ProfileNotFound as e:
        return False, f"Profile '{AWSConfig.MANAGEMENT_ACCOUNT_PROFILE}' not found", None
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'InvalidClientTokenId':
            return False, "Invalid AWS credentials", None
        elif error_code == 'ExpiredToken':
            return False, "AWS credentials have expired", None
        else:
            return False, f"AWS error: {error_code}", None
    except Exception as e:
        return False, f"Configuration error: {str(e)}", None
```

---

## Key Changes:

1. **`is_running_in_ecs()`** - Detects ECS environment by checking metadata URIs
2. **`get_session()`** - Automatically uses Task IAM Role in ECS, profile locally
3. **No profile required in ECS** - boto3 automatically picks up task role credentials
