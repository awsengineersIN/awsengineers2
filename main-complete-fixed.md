# Updated main.py (Complete Fixed Version)

Save this as: `main.py`

```python
"""
AWS Multi-Account Dashboard - Main Entry Point

Simplified architecture:
- Single authentication method: AssumeRole to READONLY_ROLE_NAME
- Merged modules into aws_helper.py
- Common sidebar across all pages
- Persistent account selection
"""

import streamlit as st
from modules.aws_helper import AWSConfig, AWSOrganizations, validate_aws_config
from modules.sidebar_common import render_sidebar

# Page configuration
st.set_page_config(
    page_title="AWS Multi-Account Dashboard",
    page_icon="🌩️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #FF9900;
        margin-bottom: 10px;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'all_accounts' not in st.session_state:
    st.session_state.all_accounts = []

# Header
st.markdown('<p class="main-header">🌩️ AWS Multi-Account Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Centralized view for all AWS resources</p>', unsafe_allow_html=True)

# Validate credentials
is_valid, message, account_id = validate_aws_config()

if is_valid:
    st.success(message)
else:
    st.error(message)
    st.error("❌ Unable to authenticate with AWS")
    st.info("""
    **Required Environment Variables:**
    - `MANAGEMENT_ACCOUNT_ID` - Your management account ID
    - `READONLY_ROLE_NAME` - IAM role name to assume (default: ReadOnlyRole)
    
    **Required Permissions:**
    - Base credentials must have `sts:AssumeRole` permission
    - Target role must trust your base credentials
    """)
    st.stop()

# Load accounts
try:
    if not st.session_state.all_accounts:
        with st.spinner("Loading AWS accounts from Organizations..."):
            st.session_state.all_accounts = AWSOrganizations.list_accounts()
    
    all_accounts = st.session_state.all_accounts
    
    if not all_accounts:
        st.error("❌ No active accounts found in AWS Organizations")
        st.stop()
    
    st.info(f"✅ Found {len(all_accounts)} active account(s)")
    
except Exception as e:
    st.error(f"❌ Error loading accounts: {str(e)}")
    st.stop()

# Store accounts for use in pages
st.session_state.accounts = all_accounts

# ============================================================================
# SIDEBAR CONFIGURATION
# ============================================================================

# Render sidebar configuration (returns account_ids and regions)
selected_account_ids, selected_regions = render_sidebar(page_key_prefix="main_")

# Check if fetch button was clicked (stored in session state by render_sidebar)
if st.session_state.get('main_fetch_clicked', False):
    st.success("✅ Configuration updated. Navigate to a dashboard page to fetch data.")
    st.session_state.main_fetch_clicked = False

# ============================================================================
# MAIN CONTENT
# ============================================================================

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Available Dashboards")
    st.markdown("""
    - **EC2 Details**: Monitor EC2 instances across accounts and regions
    - **Security Hub**: View security findings and compliance status
    - **AWS Config**: Track configuration compliance and rules
    - **IAM Key Rotation**: Monitor access key age and rotation status
    
    Select a dashboard from the navigation menu to get started.
    """)

with col2:
    st.subheader("🚀 Features")
    st.markdown("""
    - **Unified authentication**: AssumeRole to ReadOnlyRole everywhere
    - **Persistent selections**: Account/region choices persist across pages
    - **Multi-account support**: Scan resources across all AWS accounts
    - **Cross-region discovery**: Find resources in all AWS regions
    - **CSV export**: Download results for further analysis
    """)

# Quick Stats
st.markdown("---")
st.subheader("📈 Organization Summary")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total Accounts", len(all_accounts))

with col2:
    st.metric("Selected Accounts", len(selected_account_ids))

with col3:
    st.metric("Management Account", account_id)

# Getting Started Guide
st.markdown("---")
with st.expander("🎯 Getting Started Guide"):
    st.markdown(f"""
    ### How to Use This Dashboard
    
    1. **Configure in Sidebar** - Select accounts and regions
    2. **Click "Fetch Data"** in sidebar
    3. **Navigate to a Dashboard** from the navigation menu
    4. **View Results** - Data will be displayed
    5. **Use "Refresh"** button on dashboard page to update data
    6. **Download CSV** for offline analysis
    
    ### Configuration
    - **Role Name**: `{AWSConfig.READONLY_ROLE_NAME}`
    - **Max Workers**: `{AWSConfig.MAX_WORKERS}`
    
    ### Tips
    - Selections persist across pages
    - Accounts are sorted alphabetically
    - Use "Common Regions" for faster scans
    - Click "Refresh" on dashboard pages to update data with same settings
    - Navigate between pages without losing your selections
    """)

# Footer
st.markdown("---")
st.caption(f"""
AWS Multi-Account Dashboard | Role: {AWSConfig.READONLY_ROLE_NAME} | Workers: {AWSConfig.MAX_WORKERS}
""")
```
