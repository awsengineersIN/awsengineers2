# ============================================================================
# UTILS.PY - Global OU Filtering (Works with existing main.py)
# FIXED: Includes ALL filters (Organization, Account, Region, Fetch Button)
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
# ORGANIZATION ACCOUNT FETCHING
# ============================================================================

@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_org2_accounts_from_ou(ou_id):
    """
    Fetch all accounts in a specific OU from AWS Organizations API
    
    Args:
        ou_id (str): The OU ID to fetch accounts from (e.g., 'ou-abc1-12345678')
    
    Returns:
        set: Account IDs in the specified OU
        
    Requires IAM permissions:
        - organizations:ListAccountsForParent
    """
    try:
        org_client = boto3.client('organizations', region_name='us-east-1')
        
        org2_accounts = set()
        
        # Get direct accounts in this OU
        paginator = org_client.get_paginator('list_accounts_for_parent')
        for page in paginator.paginate(ParentId=ou_id):
            for account in page.get('Accounts', []):
                org2_accounts.add(account['Id'])
        
        return org2_accounts
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ParentNotFoundException':
            st.error(f"❌ OU ID not found: {ou_id}")
        elif error_code == 'AccessDeniedException':
            st.error("❌ Missing IAM permission: organizations:ListAccountsForParent")
        else:
            st.error(f"❌ AWS Error: {error_code}")
        return set()
    except Exception as e:
        st.error(f"❌ Error fetching OU accounts: {str(e)}")
        return set()


def get_org2_accounts(ou_id):
    """
    Get Org2 accounts with caching
    
    Args:
        ou_id (str): OU ID for Org2
        
    Returns:
        set: Account IDs in Org2
    """
    if not ou_id:
        return set()
        
    cache_key = f'org2_accounts_{ou_id}'
    
    if cache_key not in st.session_state:
        st.session_state[cache_key] = fetch_org2_accounts_from_ou(ou_id)
    
    return st.session_state[cache_key]


# ============================================================================
# ENHANCED setup_account_filter() - Global OU Filtering for ALL Pages
# ============================================================================

def setup_account_filter(page_key="default", org2_ou_id=None):
    """
    Enhanced account filter with automatic OU-based organization selection
    Works automatically for all dashboards!
    
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
    """
    
    # Use provided ou_id, fall back to global setting
    active_ou_id = org2_ou_id if org2_ou_id is not None else ORG2_OU_ID
    
    all_accounts = st.session_state.get('accounts', [])
    
    # =====================================================================
    # STEP 1: Organization Selection (Radio Buttons) - OPTIONAL
    # =====================================================================
    
    if active_ou_id:
        st.sidebar.subheader("📊 Organization Filter")
        
        org_selection = st.sidebar.radio(
            "Select Organization:",
            options=["Org1 (All Except Org2)", "Org2 (OU Accounts)"],
            key=f"{page_key}_org_selection",
            help="Org1: All accounts except those in the specified OU\nOrg2: Only accounts in the specified OU"
        )
        
        # Fetch Org2 accounts dynamically from AWS Organizations
        org2_accounts = get_org2_accounts(active_ou_id)
        
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
    
    account_names = [acc.get('name', acc.get('id')) for acc in filtered_accounts]
    account_ids_list = [acc.get('id') for acc in filtered_accounts]
    
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
    # STEP 3: Region Selection (Multi-select)
    # =====================================================================
    st.sidebar.subheader("🌐 Region Selection")
    
    all_regions = [
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
        'eu-west-1', 'eu-central-1', 'eu-north-1',
        'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1', 'ap-south-1'
    ]
    
    st.sidebar.caption(f"Available: {len(all_regions)} region(s)")
    
    # "Select All Regions" checkbox
    select_all_regions_checked = st.sidebar.checkbox(
        "✅ Select All Regions",
        value=True,
        key=f"{page_key}_select_all_regions"
    )
    
    if select_all_regions_checked:
        selected_regions = st.sidebar.multiselect(
            "Regions:",
            options=all_regions,
            default=all_regions,
            key=f"{page_key}_region_select"
        )
    else:
        selected_regions = st.sidebar.multiselect(
            "Regions:",
            options=all_regions,
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
