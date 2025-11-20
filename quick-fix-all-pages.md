# Quick Fix for All Dashboard Pages

## The Problem
Line causing error in all dashboard pages:
```python
default_account = st.session_state.get('selected_account', {}).get('full_name')
```

This fails when `selected_account` is `None` because `None.get('full_name')` throws AttributeError.

---

## The Solution

Replace the problematic line in **ALL** dashboard pages with this safe version:

### Find This (around line 46):
```python
default_account = st.session_state.get('selected_account', {}).get('full_name')
default_idx = 0
if default_account and default_account in account_options:
    default_idx = list(account_options.keys()).index(default_account)
```

### Replace With This:
```python
# FIX: Handle missing selected_account gracefully
default_account = None
if st.session_state.get('selected_account') is not None:
    default_account = st.session_state.get('selected_account', {}).get('full_name')

default_idx = 0
if default_account and default_account in account_options:
    default_idx = list(account_options.keys()).index(default_account)
```

---

## Files That Need This Fix

Apply this fix to ALL these dashboard pages:

1. ✅ `pages/EC2_details.py` (already provided fixed version above)
2. ⚠️ `pages/Security_Hub.py` (line ~46)
3. ⚠️ `pages/AWS_Config.py` (line ~46)
4. ⚠️ `pages/IAM_Key_Rotation.py` (line ~46)

---

## Alternative: Simpler One-Line Fix

If you prefer a simpler approach, you can also use this one-liner:

### Find:
```python
default_account = st.session_state.get('selected_account', {}).get('full_name')
```

### Replace With:
```python
default_account = st.session_state.get('selected_account', {}).get('full_name') if st.session_state.get('selected_account') else None
```

---

## Why This Happened

When you removed the configuration sidebar from `main.py`, the `selected_account` object is no longer being initialized. The dashboard pages were expecting it to be a dictionary, but it's now `None`.

The fix checks if `selected_account` exists before trying to access its `full_name` property.

---

## Quick Script to Fix All Files

If you want to automate the fix, here's a Python script:

```python
import re

files_to_fix = [
    'pages/EC2_details.py',
    'pages/Security_Hub.py',
    'pages/AWS_Config.py',
    'pages/IAM_Key_Rotation.py'
]

old_pattern = r"default_account = st\.session_state\.get\('selected_account', \{\}\)\.get\('full_name'\)"

new_code = """# FIX: Handle missing selected_account gracefully
    default_account = None
    if st.session_state.get('selected_account') is not None:
        default_account = st.session_state.get('selected_account', {}).get('full_name')"""

for file_path in files_to_fix:
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if re.search(old_pattern, content):
            content = re.sub(old_pattern, new_code, content)
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            print(f"✅ Fixed: {file_path}")
        else:
            print(f"⏭️  Skipped (pattern not found): {file_path}")
    except FileNotFoundError:
        print(f"❌ Not found: {file_path}")
    except Exception as e:
        print(f"❌ Error fixing {file_path}: {str(e)}")
```

---

## Test After Fix

After applying the fix, restart your ECS service and verify:

1. Navigate to any dashboard page
2. Account dropdown should work without errors
3. Select accounts and fetch data
4. No more NoneType errors!
