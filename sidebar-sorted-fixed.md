# Updated Sidebar Common (Alphabetically Sorted Accounts + Fixed Fetch Button)

Save this as: `modules/sidebar_common.py`

```python
"""
Common sidebar configuration for all dashboard pages.

Provides:
- Account selection (single/multiple) - alphabetically sorted
- Region selection (common/all/custom)
- Persistent selection across pages via session state
- Fetch button in sidebar
"""

import streamlit as st
from modules.aws_helper import AWSRegions

def render_sidebar(page_key_prefix=""):
    """
    Render common sidebar configuration.
    
    Args:
        page_key_prefix: Unique prefix for widget keys (e.g., "ec2_", "sh_")
        
    Returns:
        tuple: (selected_account_ids, selected_regions)
    """
    st.sidebar.header("⚙️ Configuration")
    
    # Get all accounts from session state
    all_accounts = st.session_state.get('accounts', [])
    if not all_accounts:
        st.error("No accounts found. Please return to main page.")
        st.stop()
    
    # ========================================================================
    # ACCOUNT SELECTION
    # ========================================================================
    st.sidebar.subheader("📋 Account Selection")
    
    # Sort accounts alphabetically by name
    sorted_accounts = sorted(all_accounts, key=lambda x: x['Name'].lower())
    account_options = {f"{acc['Name']} ({acc['Id']})": acc['Id'] for acc in sorted_accounts}
    
    # Initialize selected accounts in session state if not exists
    if 'selected_accounts' not in st.session_state:
        st.session_state.selected_accounts = [list(account_options.keys())[0]] if account_options else []
    
    # Select all checkbox
    select_all = st.sidebar.checkbox(
        "Select All Accounts",
        value=False,
        key=f"{page_key_prefix}select_all"
    )
    
    if select_all:
        selected_account_names = list(account_options.keys())
    else:
        # Use persistent selection from session state
        selected_account_names = st.sidebar.multiselect(
            "Choose Accounts:",
            options=list(account_options.keys()),
            default=st.session_state.selected_accounts,
            help="Select one or more accounts",
            key=f"{page_key_prefix}accounts"
        )
        
        # Update session state with current selection
        st.session_state.selected_accounts = selected_account_names
    
    selected_account_ids = [account_options[name] for name in selected_account_names]
    
    # ========================================================================
    # REGION SELECTION
    # ========================================================================
    st.sidebar.subheader("🌍 Region Selection")
    
    # Initialize selected region mode in session state
    if 'region_mode' not in st.session_state:
        st.session_state.region_mode = "Common Regions"
    
    region_mode = st.sidebar.radio(
        "Region Mode:",
        ["Common Regions", "All Regions", "Custom Regions"],
        index=["Common Regions", "All Regions", "Custom Regions"].index(st.session_state.region_mode),
        help="Choose region scanning mode",
        key=f"{page_key_prefix}region_mode"
    )
    
    # Update session state
    st.session_state.region_mode = region_mode
    
    try:
        if region_mode == "Common Regions":
            selected_regions = AWSRegions.get_common_regions()
            st.sidebar.info(f"Scanning {len(selected_regions)} common regions")
        elif region_mode == "All Regions":
            selected_regions = AWSRegions.list_all_regions()
            st.sidebar.info(f"Scanning all {len(selected_regions)} regions")
        else:  # Custom Regions
            all_regions = AWSRegions.list_all_regions()
            
            # Initialize custom regions in session state
            if 'custom_regions' not in st.session_state:
                st.session_state.custom_regions = ['us-east-1', 'us-west-2']
            
            selected_regions = st.sidebar.multiselect(
                "Select Regions:",
                options=all_regions,
                default=st.session_state.custom_regions,
                key=f"{page_key_prefix}regions"
            )
            
            # Update session state
            st.session_state.custom_regions = selected_regions
            
    except Exception as e:
        st.sidebar.error(f"Error loading regions: {str(e)}")
        st.stop()
    
    # ========================================================================
    # FETCH BUTTON
    # ========================================================================
    st.sidebar.markdown("---")
    
    fetch_button = st.sidebar.button(
        "🔄 Fetch Data",
        type="primary",
        use_container_width=True,
        key=f"{page_key_prefix}fetch"
    )
    
    # Store fetch button state for main page
    if fetch_button:
        st.session_state[f'{page_key_prefix}fetch_clicked'] = True
    
    return selected_account_ids, selected_regions
```

---

## Key Changes

1. **Sorted accounts alphabetically** - `sorted_accounts = sorted(all_accounts, key=lambda x: x['Name'].lower())`
2. **Integrated fetch button** - Fetch button is now part of render_sidebar()
3. **Fixed return value** - Always returns tuple (account_ids, regions)
4. **Removed render_fetch_button()** - No longer needed as it's integrated
