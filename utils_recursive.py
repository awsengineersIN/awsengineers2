# ============================================================================
# UTILS.PY - Global OU Filtering with Recursive OU Traversal
# FIXED: Handles nested OUs - traverses entire OU tree to find all accounts
# ============================================================================

import streamlit as st
import boto3
from botocore.exceptions import ClientError

# ============================================================================
# GLOBAL ORGANIZATION CONFIGURATION
# ============================================================================
# SET YOUR OU ID HERE - This applies to ALL dashboards automatically!

ORG2_OU_ID = "ou-abc1-12345678"  # Replace with YOUR actual OU ID for Org2
                                  # Set to None to disable OU filtering globally

# ============================================================================
# COMMON REGIONS (from your existing setup)
# ============================================================================

COMMON_REGIONS = [
    'us-east-1',
    'us-west-2'
]

# ============================================================================
# RECURSIVE OU ACCOUNT FETCHING - Handles Nested OUs
# ============================================================================

@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_all_accounts_in_ou_tree(ou_id):
    """
    Recursively fetch all accounts in an OU and all child OUs.
    Handles nested OU structure:
    
    Org2 OU
    ├── Child OU 1
    │   ├── Child OU 1.1
    │   │   ├── Account A
    │   │   └── Account B
    │   └── Child OU 1.2
    │       ├── Account C
    │       └── Account D
    └── Child OU 2
        ├── Account E
        └── Account F
    
    Args:
        ou_id (str): Root OU ID to start traversal from
    
    Returns:
        set: All account IDs found in this OU and all nested child OUs
        
    Requires IAM permissions:
        - organizations:ListAccountsForParent
        - organizations:ListOrganizationalUnitsForParent
    """
    try:
        org_client = boto3.client('organizations', region_name='us-east-1')
        all_accounts = set()
        
        def traverse_ou(parent_id):
            """
            Recursively traverse OUs and collect accounts
            
            Args:
                parent_id (str): Parent ID to traverse (OU or Root)
            """
            # Get all direct accounts in this OU
            paginator = org_client.get_paginator('list_accounts_for_parent')
            try:
                for page in paginator.paginate(ParentId=parent_id):
                    for account in page.get('Accounts', []):
                        all_accounts.add(account['Id'])
            except ClientError as e:
                # If this fails, continue to next parent
                pass
            
            # Get all child OUs and recurse
            try:
                child_paginator = org_client.get_paginator('list_organizational_units_for_parent')
                for page in child_paginator.paginate(ParentId=parent_id):
                    for child_ou in page.get('OrganizationalUnits', []):
                        # Recursively traverse this child OU
                        traverse_ou(child_ou['Id'])
            except ClientError as e:
                # If this fails, continue
                pass
        
        # Start traversal from the given OU ID
        traverse_ou(ou_id)
        
        return all_accounts
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ParentNotFoundException':
            st.error(f"❌ OU ID not found: {ou_id}")
        elif error_code == 'AccessDeniedException':
            st.error("❌ Missing IAM permissions: organizations:ListAccountsForParent or organizations:ListOrganizationalUnitsForParent")
        else:
            st.error(f"❌ AWS Error: {error_code}")
        return set()
    except Exception as e:
        st.error(f"❌ Error fetching OU accounts: {str(e)}")
        return set()


def get_org2_accounts(ou_id):
    """
    Get Org2 accounts with caching (includes all nested OUs)
    
    Args:
        ou_id (str): OU ID for Org2
        
    Returns:
        set: Account IDs in Org2 (including all nested child OUs)
    """
    if not ou_id:
        return set()
        
    cache_key = f'org2_accounts_{ou_id}'
    
    if cache_key not in st.session_state:
        st.session_state[cache_key] = fetch_all_accounts_in_ou_tree(ou_id)
    
    return st.session_state[cache_key]


# ============================================================================
# ENHANCED setup_account_filter() - Global OU Filtering for ALL Pages
# ============================================================================

def setup_account_filter(page_key="default", org2_ou_id=None):
    """
    Enhanced account filter with automatic OU-based organization selection
    Handles nested OU structures automatically!
    
    🎯 Assumes st.session_state['accounts'] is populated by main.py
    
    Args:
        page_key (str): Unique key for this filter instance (e.g., 'patch', 'ecs')
        org2_ou_id (str): (Optional) Override global OU ID for this page only
                         If not provided, uses ORG2_OU_ID from this file
    
    Returns:
        tuple: (account_ids, regions) - filtered by selected organization
        
    Example - NO CHANGES NEEDED IN YOUR DASHBOARDS:
        # In patch_compliance.py - stays exactly the same!
        account_ids, regions = setup_account_filter(page_key="patch")
        
        # In ECS-3.py - stays exactly the same!
        account_ids, regions = setup_account_filter(page_key="ecs")
        
        # OU filtering automatically applied to all pages!
        # Nested OUs are automatically handled!
    """
    
    # Use provided ou_id, fall back to global setting
    active_ou_id = org2_ou_id if org2_ou_id is not None else ORG2_OU_ID
    
    all_accounts = st.session_state.get('accounts', [])
    
    # =====================================================================
    # DEBUG: Show account structure (Uncomment to debug)
    # =====================================================================
    # st.sidebar.write("DEBUG - Account structure:")
    # if all_accounts:
    #     st.sidebar.write(f"First account: {all_accounts[0]}")
    
    # =====================================================================
    # STEP 1: Organization Selection (Radio Buttons) - OPTIONAL
    # =====================================================================
    
    if active_ou_id:
        st.sidebar.subheader("📊 Organization Filter")
        
        org_selection = st.sidebar.radio(
            "Select Organization:",
            options=["Org1 (All Except Org2)", "Org2 (OU Accounts)"],
            key=f"{page_key}_org_selection",
            help="Org1: All accounts except those in Org2 OU tree\nOrg2: All accounts in Org2 OU and all nested child OUs"
        )
        
        # Fetch Org2 accounts dynamically from AWS Organizations (with nested OU traversal)
        org2_accounts = get_org2_accounts(active_ou_id)
        
        # Debug: Show OU account IDs
        # st.sidebar.write(f"DEBUG - Org2 accounts in OU tree: {org2_accounts}")
        
        # Filter accounts based on organization selection
        if org_selection == "Org2 (OU Accounts)":
            filtered_accounts = [acc for acc in all_accounts if acc.get('id') in org2_accounts]
            org_count = len(filtered_accounts)
            org_label = "Org2"
        else:
            filtered_accounts = [acc for acc in all_accounts if acc.get('id') not in org2_accounts]
            org_count = len(filtered_accounts)
            org_label = "Org1"
        
        st.sidebar.caption(f"📍 {org_label}: {org_count} account(s)")
        st.sidebar.markdown("---")
    else:
        # No OU filtering - use all accounts
        filtered_accounts = all_accounts
    
    # =====================================================================
    # STEP 2: Account Selection (Multi-select)
    # =====================================================================
    st.sidebar.subheader("🏢 Account Selection")
    
    # FIX: Handle account names properly (multiple formats)
    account_names = []
    account_ids_list = []
    
    for acc in filtered_accounts:
        # Try different ways to get account name
        if isinstance(acc, dict):
            acc_name = acc.get('name') or acc.get('Name') or acc.get('id') or 'Unknown'
        else:
            # If it's an object
            acc_name = getattr(acc, 'name', None) or getattr(acc, 'Name', None) or getattr(acc, 'id', 'Unknown')
        
        acc_id = acc.get('id') if isinstance(acc, dict) else getattr(acc, 'id', '')
        
        account_names.append(acc_name)
        account_ids_list.append(acc_id)
    
    # Display account count
    st.sidebar.caption(f"Available: {len(account_names)} account(s)")
    
    # "Select All" checkbox
    select_all_checked = st.sidebar.checkbox(
        "✅ Select All Accounts",
        value=True,
        key=f"{page_key}_select_all_accounts"
    )
    
    if select_all_checked:
        selected_accounts = st.sidebar.multiselect(
            "Accounts:",
            options=account_names,
            default=account_names,
            key=f"{page_key}_account_select"
        )
    else:
        selected_accounts = st.sidebar.multiselect(
            "Accounts:",
            options=account_names,
            key=f"{page_key}_account_select"
        )
    
    # Map selected account names back to IDs
    selected_account_ids = [
        aid for acc_name, aid in zip(account_names, account_ids_list)
        if acc_name in selected_accounts
    ]
    
    st.sidebar.markdown("---")
    
    # =====================================================================
    # STEP 3: Region Selection (Multi-select) - Using COMMON_REGIONS
    # =====================================================================
    st.sidebar.subheader("🌐 Region Selection")
    
    st.sidebar.caption(f"Available: {len(COMMON_REGIONS)} region(s)")
    
    # "Select All Regions" checkbox
    select_all_regions_checked = st.sidebar.checkbox(
        "✅ Select All Regions",
        value=True,
        key=f"{page_key}_select_all_regions"
    )
    
    if select_all_regions_checked:
        selected_regions = st.sidebar.multiselect(
            "Regions:",
            options=COMMON_REGIONS,
            default=COMMON_REGIONS,
            key=f"{page_key}_region_select"
        )
    else:
        selected_regions = st.sidebar.multiselect(
            "Regions:",
            options=COMMON_REGIONS,
            key=f"{page_key}_region_select"
        )
    
    st.sidebar.markdown("---")
    
    # =====================================================================
    # STEP 4: Fetch Button & Flag Management
    # =====================================================================
    st.sidebar.subheader("🔄 Actions")
    
    if st.sidebar.button(
        "📊 Fetch Data",
        type="primary",
        use_container_width=True,
        key=f"{page_key}_fetch_button"
    ):
        st.session_state[f'{page_key}_fetch_clicked'] = True
        st.rerun()
    
    return selected_account_ids, selected_regions


# ============================================================================
# REST OF YOUR UTILS.PY FUNCTIONS
# ============================================================================
# Keep all your existing functions like:
# - assume_role()
# - get_account_name_by_id()
# - etc.
