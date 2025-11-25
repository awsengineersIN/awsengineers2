# Quick Reference: Dashboard Updates for utils.py

## 🔄 3 Simple Changes Per Dashboard

### 1️⃣ Update Imports (Top of File)

**REMOVE:**
```python
from modules.aws_helper import AWSConfig, AWSOrganizations, AWSSession
from modules.sidebar_simple import render_sidebar
```

**ADD:**
```python
from utils import assume_role, setup_account_filter, get_account_name_by_id
import boto3
```

---

### 2️⃣ Update Sidebar Call

**REPLACE:**
```python
account_ids, regions = render_sidebar(page_key="your_service")
```

**WITH:**
```python
account_ids, regions = setup_account_filter(page_key="your_service")
```

---

### 3️⃣ Create Client Helper & Update Data Function

**ADD THIS HELPER FUNCTION** (once per AWS service):

```python
def get_[service]_client(account_id, role_name, region):
    """Get [Service] client using utils.py assume_role"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        '[service_name]',  # e.g., 'securityhub', 'iam', 'config'
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )
```

**UPDATE YOUR DATA FUNCTION:**

**OLD:**
```python
def get_service_data(region, account_id, account_name, role_name):
    data = []
    errors = []
    
    try:
        client = AWSSession.get_client_for_account('service', account_id, role_name, region)
        # ... rest of logic
```

**NEW:**
```python
def get_service_data(region, account_id, account_name, role_name):
    data = []
    errors = []
    
    try:
        client = get_[service]_client(account_id, role_name, region)
        if not client:
            errors.append(f"❌ {account_name}/{region}: Failed to get client")
            return data, errors
        # ... rest of logic (unchanged)
```

---

## 📋 Service-Specific Client Helpers

Copy/paste these as needed:

### Security Hub
```python
def get_securityhub_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('securityhub', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])
```

### IAM (Global Service)
```python
def get_iam_client(account_id, role_name):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('iam', region_name='us-east-1',
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])
```

### AWS Config
```python
def get_config_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('config', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])
```

### AWS Backup
```python
def get_backup_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('backup', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])
```

### EC2
```python
def get_ec2_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('ec2', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])
```

---

## 🔍 Other Small Changes

### Account Name Lookup

**REPLACE:**
```python
account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
```

**WITH:**
```python
account_name = get_account_name_by_id(account_id, all_accounts)
```

### Role Name

**REPLACE:**
```python
role_name = AWSConfig.READONLY_ROLE_NAME
```

**WITH:**
```python
role_name = "readonly-role"
```

---

## ✅ Example: Complete Security Hub Migration

**BEFORE:**
```python
from modules.aws_helper import AWSConfig, AWSOrganizations, AWSSession
from modules.sidebar_simple import render_sidebar

account_ids, regions = render_sidebar(page_key="securityhub")

def get_security_hub_findings(region, account_id, account_name, role_name):
    findings = []
    errors = []
    try:
        sh_client = AWSSession.get_client_for_account('securityhub', account_id, role_name, region)
        # ... fetch logic
    except Exception as e:
        errors.append(f"❌ Error: {str(e)}")
    return findings, errors

# Fetch
account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
data = get_security_hub_findings(region, account_id, account_name, AWSConfig.READONLY_ROLE_NAME)
```

**AFTER:**
```python
from utils import assume_role, setup_account_filter, get_account_name_by_id
import boto3

account_ids, regions = setup_account_filter(page_key="securityhub")

def get_securityhub_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('securityhub', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])

def get_security_hub_findings(region, account_id, account_name, role_name):
    findings = []
    errors = []
    try:
        sh_client = get_securityhub_client(account_id, role_name, region)
        if not sh_client:
            errors.append(f"❌ {account_name}/{region}: Failed to get client")
            return findings, errors
        # ... fetch logic (unchanged)
    except Exception as e:
        errors.append(f"❌ Error: {str(e)}")
    return findings, errors

# Fetch
account_name = get_account_name_by_id(account_id, all_accounts)
data = get_security_hub_findings(region, account_id, account_name, "readonly-role")
```

---

## 📦 What Stays The Same

✅ Session state management
✅ Parallel processing (ThreadPoolExecutor)
✅ Progress bars and status tracking
✅ Button click handling (`_fetch_clicked`)
✅ Data display and filtering
✅ Metrics and summary
✅ CSV export
✅ Debug mode
✅ All business logic

**Only the AWS client creation changes!**

---

## 🚀 Migration Steps

1. Open dashboard file
2. Update imports (copy/paste from above)
3. Change sidebar call
4. Add client helper function(s) for services you use
5. Update client creation in data functions
6. Update account name lookups
7. Update role name references
8. Test!

**Time per dashboard: ~5-10 minutes**

---

## 🐛 Troubleshooting

**"Failed to get client" errors:**
- Check that `assume_role()` is working
- Verify role name is "readonly-role" in all accounts
- Check trust relationship in target accounts

**"No module named 'utils'" error:**
- Make sure `utils.py` is in the same directory as your dashboard
- Or add utils path to sys.path

**"AttributeError: 'NoneType' has no attribute" error:**
- Client creation returned None
- Add the `if not client: return` check

---

## 📞 Need More Help?

See the complete Migration Guide PDF [150] for:
- Detailed explanations
- Full file examples
- Service-specific patterns
- Testing checklist
- Common issues and solutions

---

**Summary: Just 3 changes per file - imports, sidebar, and client helpers. Everything else stays identical!**
