# ============================================================================
# MINIMAL PATCH: Add CenterOne Support - Keep Everything Else Unchanged
# ============================================================================

## **What to Do:**

Add ONLY these new functions to your existing utils.py (after get_organization_accounts function):

```python
# ============================================================================
# CENTERONE OU FILTERING FUNCTIONS - ADD THIS SECTION ONLY
# ============================================================================

@lru_cache(maxsize=1)
def get_org_client():
    """Get cached organizations client"""
    return boto3.client('organizations', region_name='us-east-1')


@st.cache_data(ttl=3600)
def find_ou_by_name(ou_name, parent_id=None):
    """
    Find OU by name recursively.
    Returns: OU ID if found, None if not found
    """
    org_client = get_org_client()
    
    try:
        if parent_id is None:
            response = org_client.list_roots()
            parent_id = response['Roots'][0]['Id']
        
        try:
            response = org_client.list_organizational_units_for_parent(ParentId=parent_id)
        except Exception:
            return None
        
        for ou in response.get('OrganizationalUnits', []):
            if ou['Name'] == ou_name:
                return ou['Id']
            
            found_id = find_ou_by_name(ou_name, ou['Id'])
            if found_id:
                return found_id
        
        return None
        
    except Exception as e:
        print(f"Error finding OU: {str(e)}")
        return None


@st.cache_data(ttl=3600)
def fetch_accounts_in_ou_tree(ou_id):
    """
    Recursively fetch all accounts in OU tree.
    Returns: dict {account_id: {Id, Name, Status, ...}}
    """
    org_client = get_org_client()
    all_accounts = {}
    
    def traverse_ou(parent_id):
        try:
            response = org_client.list_accounts_for_parent(ParentId=parent_id)
            for account in response.get('Accounts', []):
                all_accounts[account['Id']] = account
        except Exception:
            pass
        
        try:
            response = org_client.list_organizational_units_for_parent(ParentId=parent_id)
            for ou in response.get('OrganizationalUnits', []):
                traverse_ou(ou['Id'])
        except Exception:
            pass
    
    try:
        traverse_ou(ou_id)
    except Exception as e:
        print(f"Error traversing OU: {str(e)}")
    
    return all_accounts


@st.cache_data(ttl=3600)
def get_centerone_accounts():
    """Get all accounts under CenterOne OU"""
    CENTERONE_OU_NAME = "CenterOne"
    centerone_ou_id = find_ou_by_name(CENTERONE_OU_NAME)
    
    if not centerone_ou_id:
        return {}
    
    return fetch_accounts_in_ou_tree(centerone_ou_id)
```

---

## **Then ONLY Update setup_account_filter():**

Find your current `setup_account_filter()` function and replace it with this:

```python
def setup_account_filter(page_key=""):
    st.sidebar.header("⚙️ Configuration")
    
    # Get accounts from session or default list
    accounts = st.session_state.get("accounts", [])
    centerone_accounts_dict = get_centerone_accounts()  # NEW LINE
    
    if not accounts:
        st.sidebar.error("No accounts loaded")
        return [], []
    
    accounts = sorted(accounts, key=lambda x: x["Name"])
    
    # NEW: Split accounts into Org1 and CenterOne
    centerone_account_ids = set(centerone_accounts_dict.keys())
    org1_accounts = [acc for acc in accounts if acc['Id'] not in centerone_account_ids]
    centerone_accounts_filtered = [acc for acc in accounts if acc['Id'] in centerone_account_ids]
    
    st.sidebar.subheader("👥 Organization")  # NEW
    org_choice = st.sidebar.radio(  # NEW
        "Select Organization:",
        options=["Org1 (All Except CenterOne)", "CenterOne"],
        key=f"{page_key}_org_choice"
    )
    
    # NEW: Choose accounts based on org selection
    if org_choice == "CenterOne":
        selected_accounts_list = centerone_accounts_filtered
        st.sidebar.info(f"✅ CenterOne: {len(centerone_accounts_filtered)} accounts")
    else:
        selected_accounts_list = org1_accounts
        st.sidebar.info(f"✅ Org1: {len(org1_accounts)} accounts")
    
    st.sidebar.subheader("👥 Accounts")
    account_names = [f"{acc['Name']} ({acc['Id']})" for acc in selected_accounts_list]
    account_ids = [acc["Id"] for acc in selected_accounts_list]
    
    select_all_key = f"{page_key}_select_all_accounts"
    if select_all_key not in st.session_state:
        st.session_state[select_all_key] = True
    
    select_all = st.sidebar.checkbox(
        "Select All Accounts",
        value=st.session_state[select_all_key],
        key=f"{page_key}_select_all_cb",
    )
    
    st.session_state[select_all_key] = select_all
    
    if select_all:
        st.sidebar.info("✅ All accounts selected")
        selected_account_id = account_ids
    else:
        selected_names = st.sidebar.multiselect(
            "Choose accounts:",
            options=account_names,
            default=[],
            key=f"{page_key}_accounts"
        )
        
        selected_account_id = [
            account_ids[account_names.index(name)] for name in selected_names
        ]
    
    st.sidebar.subheader("🌍 Regions")
    region_mode = st.sidebar.radio(
        "Region mode:", ["Common", "All"],
        key=f"{page_key}_region_mode"
    )
    
    if region_mode == "Common":
        DEFAULT_REGIONS = ["us-east-1", "us-west-2"]
        selected_regions = st.sidebar.multiselect(
            "Select regions:",
            options=DEFAULT_REGIONS,
            default=DEFAULT_REGIONS,
            key=f"{page_key}_regions",
        )
    elif region_mode == "All":
        all_regions = get_all_regions()
        DEFAULT_REGIONS = ["us-east-1", "us-west-2"]
        selected_regions = st.sidebar.multiselect(
            "Select regions:",
            options=all_regions,
            default=DEFAULT_REGIONS,
            key=f"{page_key}_regions_all",
        )
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button(
        "Fetch Data",
        type="primary",
        use_container_width=True,
        key=f"{page_key}_fetch"
    ):
        st.session_state[f"{page_key}_fetch_clicked"] = True
        st.rerun()
    
    return selected_account_id, selected_regions
```

---

## **Summary of Changes:**

✅ **Added 3 NEW functions:**
- `get_org_client()`
- `find_ou_by_name()`
- `fetch_accounts_in_ou_tree()`
- `get_centerone_accounts()`

✅ **Modified ONLY `setup_account_filter()`:**
- Added organization radio button (Org1 vs CenterOne)
- Split accounts based on org selection
- Keep ALL existing UI look and feel

❌ **NO CHANGES to:**
- `get_organization_hierarchy()`
- `get_organization_accounts()`
- `assume_role()`
- `get_all_regions()`
- `get_account_name_by_id()`
- Any other functions

---

## **Implementation:**

1. **Add the 4 NEW functions** after `get_organization_accounts()`

2. **Replace ONLY `setup_account_filter()`** with the updated version

3. **Add at top of file (with existing imports):**
```python
from functools import lru_cache
```

4. **Restart streamlit**

That's it! Minimal, focused change. ✅
