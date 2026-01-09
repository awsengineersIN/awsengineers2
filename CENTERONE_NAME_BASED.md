# ============================================================================
# SOLUTION: Find OU by Name "CenterOne" and Get All Accounts Recursively
# ============================================================================

## **🎯 New Approach**

Instead of hardcoding OU IDs, we'll:
1. **Find the OU named "CenterOne"** (regardless of where it is)
2. **Recursively get all accounts** under it
3. This works at ANY nesting level

---

## **✅ New utils.py Function**

Replace the old `fetch_all_accounts_in_ou_tree()` with this:

```python
import boto3
import streamlit as st

# Configuration
CENTERONE_OU_NAME = "CenterOne"  # Find OU by this name
COMMON_REGIONS = ['us-east-1', 'us-west-2']

@st.cache_data(ttl=3600)
def find_ou_by_name(ou_name, parent_id=None):
    """
    Find OU by name recursively.
    Returns the OU ID if found, None if not found.
    """
    try:
        org_client = boto3.client('organizations', region_name='us-east-1')
        
        # Get root if parent not specified
        if parent_id is None:
            response = org_client.list_roots()
            parent_id = response['Roots'][0]['Id']
        
        # Search for OU at this level
        response = org_client.list_organizational_units_for_parent(ParentId=parent_id)
        
        for ou in response.get('OrganizationalUnits', []):
            # Check if this is the OU we're looking for
            if ou['Name'] == ou_name:
                return ou['Id']
            
            # If not found at this level, search child OUs
            found_id = find_ou_by_name(ou_name, ou['Id'])
            if found_id:
                return found_id
        
        return None
        
    except Exception as e:
        st.error(f"Error finding OU: {str(e)}")
        return None


@st.cache_data(ttl=3600)
def fetch_all_accounts_in_ou_tree(ou_id):
    """
    Recursively fetch all accounts in OU and child OUs.
    Works at any nesting depth.
    """
    try:
        org_client = boto3.client('organizations', region_name='us-east-1')
        all_accounts = set()
        
        def traverse_ou(parent_id):
            # Get direct accounts in this OU
            try:
                response = org_client.list_accounts_for_parent(ParentId=parent_id)
                for account in response.get('Accounts', []):
                    all_accounts.add(account['Id'])
            except Exception:
                pass
            
            # Get child OUs and recurse
            try:
                response = org_client.list_organizational_units_for_parent(ParentId=parent_id)
                for ou in response.get('OrganizationalUnits', []):
                    traverse_ou(ou['Id'])  # Recursive call
            except Exception:
                pass
        
        # Start traversal from the OU you pass in
        traverse_ou(ou_id)
        return all_accounts
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return set()


def get_org2_accounts():
    """
    Get all accounts under CenterOne OU.
    Finds OU by name, then gets all accounts recursively.
    """
    # Find CenterOne OU by name
    centerone_ou_id = find_ou_by_name(CENTERONE_OU_NAME)
    
    if not centerone_ou_id:
        return set()
    
    # Get all accounts in CenterOne tree
    accounts = fetch_all_accounts_in_ou_tree(centerone_ou_id)
    return accounts


def setup_account_filter(page_key="default", org2_ou_id=None):
    """
    Enhanced filter with Organization/Account/Region selection.
    """
    if org2_ou_id is None:
        # Find CenterOne OU dynamically
        org2_ou_id = find_ou_by_name(CENTERONE_OU_NAME)
    
    # Get all AWS accounts (for Org1 calculation)
    org_client = boto3.client('organizations', region_name='us-east-1')
    
    try:
        all_accounts_response = org_client.list_accounts()
        all_aws_accounts = {acc['Id']: acc for acc in all_accounts_response.get('Accounts', [])}
    except Exception:
        all_aws_accounts = {}
    
    # Get CenterOne accounts
    centerone_accounts = get_org2_accounts() if org2_ou_id else set()
    org1_accounts = {acc_id for acc_id in all_aws_accounts.keys() if acc_id not in centerone_accounts}
    
    # Sidebar filter
    with st.sidebar:
        st.write("📊 Organization Filter")
        
        org_choice = st.radio(
            "Select Organization",
            options=["Org1 (All Except CenterOne)", "CenterOne"],
            key=f"{page_key}_org_choice"
        )
        
        # Get appropriate accounts
        if org_choice == "CenterOne":
            selected_org_accounts = centerone_accounts
            account_list = {acc_id: all_aws_accounts.get(acc_id, {}).get('Name', acc_id) 
                          for acc_id in selected_org_accounts}
            st.write(f"✅ CenterOne: {len(selected_org_accounts)} accounts")
        else:
            selected_org_accounts = org1_accounts
            account_list = {acc_id: all_aws_accounts.get(acc_id, {}).get('Name', acc_id) 
                          for acc_id in selected_org_accounts}
            st.write(f"✅ Org1: {len(org1_accounts)} accounts")
        
        # Account selection
        st.write("🏢 Account Selection")
        all_selected = st.checkbox("Select All Accounts", value=True, key=f"{page_key}_all_accounts")
        
        if all_selected:
            selected_accounts = list(selected_org_accounts)
        else:
            selected_accounts = st.multiselect(
                "Choose Accounts",
                options=list(account_list.keys()),
                format_func=lambda x: f"{x} ({account_list[x]})",
                key=f"{page_key}_accounts"
            )
        
        # Region selection
        st.write("🌐 Region Selection")
        all_regions = st.checkbox("Select All Regions", value=True, key=f"{page_key}_all_regions")
        
        if all_regions:
            selected_regions = COMMON_REGIONS
        else:
            selected_regions = st.multiselect(
                "Choose Regions",
                options=COMMON_REGIONS,
                default=COMMON_REGIONS,
                key=f"{page_key}_regions"
            )
        
        # Fetch button
        if st.button("📊 Fetch Data", key=f"{page_key}_fetch"):
            st.session_state[f"{page_key}_fetch_clicked"] = True
    
    return selected_accounts, selected_regions
```

---

## **🔍 How It Works**

### **find_ou_by_name("CenterOne")**
```
1. Gets Root OU
2. Lists child OUs
3. For each child OU:
   ├─ Check if name == "CenterOne"
   ├─ If YES: Return OU ID ✅
   └─ If NO: Search child OUs recursively
4. Eventually finds "CenterOne" OU regardless of nesting level
```

### **fetch_all_accounts_in_ou_tree(ou_id)**
```
1. Gets the CenterOne OU ID from above
2. Recursively traverses the entire tree
3. Finds all accounts at ANY depth
4. Returns complete set
```

---

## **✅ Updated utils.py Setup**

Just replace these parts in your utils.py:

```python
# At the TOP:
CENTERONE_OU_NAME = "CenterOne"
COMMON_REGIONS = ['us-east-1', 'us-west-2']

# Replace old functions with NEW ones above:
# - find_ou_by_name()          ← NEW
# - fetch_all_accounts_in_ou_tree()  ← UPDATED (same logic)
# - get_org2_accounts()        ← UPDATED (now finds OU by name)
# - setup_account_filter()     ← UPDATED (handles dynamic OU finding)
```

---

## **🚀 Why This Works**

- ✅ **No hardcoded OU IDs** - finds by name
- ✅ **Name-based is reliable** - OU names don't change like IDs
- ✅ **Works at any nesting level** - recursion finds it anywhere
- ✅ **Automatic CenterOne detection** - even if you don't know the OU ID
- ✅ **Handles any depth** - 2 levels, 3 levels, 10 levels - all work

---

## **🧪 Test It**

In Python:

```python
import utils

# Find the OU by name
ou_id = utils.find_ou_by_name("CenterOne")
print(f"Found CenterOne OU: {ou_id}")

# Get all accounts under it
accounts = utils.fetch_all_accounts_in_ou_tree(ou_id)
print(f"Total accounts: {len(accounts)}")
print(f"Account IDs: {list(accounts)[:5]}")
```

---

## **📋 Test Commands**

To verify it works:

```bash
# Just run dashboard now:
streamlit run main.py

# Check sidebar:
# - Select "CenterOne" from org filter
# - Should show: "✅ CenterOne: X accounts"
# - Should list all accounts from CenterOne tree
```

---

## **✨ No More OU ID Hunting!**

Just set the OU name and the code handles everything! 🎉
