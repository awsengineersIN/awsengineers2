"""
Simplified Sidebar Module

Clean, minimal sidebar with easy-to-edit configuration.
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
    
    selected_names = st.sidebar.multiselect(
        "Select accounts:",
        options=account_names,
        default=account_names,
        key=f"{page_key}_accounts"
    )
    
    # Map back to IDs
    selected_ids = [
        account_ids[account_names.index(name)] 
        for name in selected_names
    ]
    
    # Region selection
    st.sidebar.subheader("🌍 Regions")
    
    region_mode = st.sidebar.radio(
        "Region mode:",
        ["Common", "All", "Custom"],
        key=f"{page_key}_region_mode"
    )
    
    if region_mode == "Common":
        selected_regions = st.sidebar.multiselect(
            "Select regions:",
            options=DEFAULT_REGIONS,
            default=DEFAULT_REGIONS,
            key=f"{page_key}_regions"
        )
    
    elif region_mode == "All":
        all_regions = get_all_regions()
        selected_regions = st.sidebar.multiselect(
            "Select regions:",
            options=all_regions,
            default=DEFAULT_REGIONS,
            key=f"{page_key}_regions_all"
        )
    
    else:  # Custom
        custom = st.sidebar.text_input(
            "Enter regions (comma-separated):",
            value="us-east-1,us-west-2",
            key=f"{page_key}_regions_custom"
        )
        selected_regions = [r.strip() for r in custom.split(',') if r.strip()]
    
    # Fetch button
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Fetch Data", type="primary", use_container_width=True, key=f"{page_key}_fetch"):
        st.session_state[f'{page_key}_fetch_clicked'] = True
        st.rerun()
    
    return selected_ids, selected_regions


# ============================================================================
# OPTIONAL: Add custom sidebar options
# ============================================================================

def add_sidebar_options(page_key, options_dict):
    """
    Add custom options to sidebar.
    
    Example:
        options = add_sidebar_options("rds", {
            "engine": {
                "type": "multiselect",
                "label": "DB Engine",
                "options": ["mysql", "postgres", "oracle"],
                "default": ["mysql", "postgres"]
            },
            "status": {
                "type": "selectbox",
                "label": "Status Filter",
                "options": ["All", "Available", "Stopped"],
                "default": "All"
            }
        })
    """
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔧 Options")
    
    results = {}
    
    for key, config in options_dict.items():
        option_type = config.get("type", "text_input")
        label = config.get("label", key)
        
        if option_type == "multiselect":
            results[key] = st.sidebar.multiselect(
                label,
                options=config.get("options", []),
                default=config.get("default", []),
                key=f"{page_key}_{key}"
            )
        
        elif option_type == "selectbox":
            results[key] = st.sidebar.selectbox(
                label,
                options=config.get("options", []),
                index=config.get("options", []).index(config.get("default", config.get("options", [""])[0])),
                key=f"{page_key}_{key}"
            )
        
        elif option_type == "slider":
            results[key] = st.sidebar.slider(
                label,
                min_value=config.get("min", 0),
                max_value=config.get("max", 100),
                value=config.get("default", 50),
                key=f"{page_key}_{key}"
            )
        
        elif option_type == "checkbox":
            results[key] = st.sidebar.checkbox(
                label,
                value=config.get("default", False),
                key=f"{page_key}_{key}"
            )
        
        else:  # text_input
            results[key] = st.sidebar.text_input(
                label,
                value=config.get("default", ""),
                key=f"{page_key}_{key}"
            )
    
    return results
