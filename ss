"""
Simplified Sidebar Module

Clean, minimal sidebar with easy-to-edit configuration.
Includes "Select All" checkbox for accounts.
"""

import streamlit as st

# ============================================================================
# CONFIGURATION - Edit these as needed
# ============================================================================

# Default regions to show
DEFAULT_REGIONS = [
    'us-east-1',
    'us-east-2',
    'us-west-1',
    'us-west-2',
    'eu-west-1',
    'eu-central-1',
    'ap-southeast-1',
    'ap-northeast-1',
]

# All available regions (fetched once, cached)
@st.cache_data
def get_all_regions():
    """Get all AWS regions - cached for performance"""
    import boto3
    try:
        ec2 = boto3.client('ec2', region_name='us-east-1')
        response = ec2.describe_regions(AllRegions=False)
        return sorted([r['RegionName'] for r in response['Regions']])
    except:
        return DEFAULT_REGIONS


# ============================================================================
# MAIN SIDEBAR FUNCTION
# ============================================================================

def render_sidebar(page_key=""):
    """
    Render sidebar with account and region selection.
    
    Args:
        page_key: Unique key prefix for this page (e.g., "ec2", "rds")
        
    Returns:
        tuple: (selected_account_ids, selected_regions)
    """
    
    st.sidebar.header("⚙️ Configuration")
    
    # Get accounts
    accounts = st.session_state.get('accounts', [])
    if not accounts:
        st.sidebar.error("No accounts loaded")
        return [], []
    
    # Sort alphabetically
    accounts = sorted(accounts, key=lambda x: x['Name'])
    
    # Account selection
    st.sidebar.subheader("📋 Accounts")
    
    account_names = [f"{acc['Name']} ({acc['Id']})" for acc in accounts]
    account_ids = [acc['Id'] for acc in accounts]
    
    # Select All checkbox
    select_all_key = f"{page_key}_select_all_accounts"
    if select_all_key not in st.session_state:
        st.session_state[select_all_key] = True
    
    select_all = st.sidebar.checkbox(
        "Select All Accounts",
        value=st.session_state[select_all_key],
        key=f"{page_key}_select_all_cb"
    )
    
    # Update session state
    st.session_state[select_all_key] = select_all
    
    # Account multiselect - disabled when "Select All" is checked
    if select_all:
        st.sidebar.info("✅ All accounts selected")
        selected_ids = account_ids  # Return all account IDs
    else:
        selected_names = st.sidebar.multiselect(
            "Choose accounts:",
            options=account_names,
            default=[],
            key=f"{page_key}_accounts"
        )
        
        # Map back to IDs
        selected_ids =
