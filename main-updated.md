# Updated Main Page (Configuration Sidebar Removed)

Save this as: `main.py`

```python
"""
AWS Multi-Account Dashboard - Main Entry Point

This is the main entry point for the Streamlit application.
It provides account discovery and page navigation for all dashboards.

Run with:
    streamlit run main.py

For local testing with credentials:
    export AWS_ACCESS_KEY_ID=your_access_key
    export AWS_SECRET_ACCESS_KEY=your_secret_key
    export AWS_SESSION_TOKEN=your_session_token
    streamlit run main.py

For profile-based authentication:
    export AWS_PROFILE=your-profile-name
    streamlit run main.py
"""

import streamlit as st
from modules.config import AWSConfig, validate_aws_config
from modules.iam import AWSOrganizations

# Configure Streamlit page
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
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'selected_account' not in st.session_state:
    st.session_state.selected_account = None
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
    st.error("❌ Unable to authenticate with AWS. Please check your credentials.")
    st.info("""
    **For Profile-Based Authentication:**
    ```bash
    export AWS_PROFILE=your-profile-name
    streamlit run main.py
    ```
    
    **For Environment Variable Authentication (Local Testing):**
    ```bash
    export AWS_ACCESS_KEY_ID=your_access_key
    export AWS_SECRET_ACCESS_KEY=your_secret_key
    export AWS_SESSION_TOKEN=your_session_token  # Optional, for STS credentials
    streamlit run main.py
    ```
    """)
    st.stop()

# Load accounts
try:
    if not st.session_state.all_accounts:
        with st.spinner("Loading AWS accounts from Organizations..."):
            st.session_state.all_accounts = AWSOrganizations.list_accounts()
    
    all_accounts = st.session_state.all_accounts
    
    if not all_accounts:
        st.error("❌ No active accounts found in AWS Organizations.")
        st.info("Ensure you have Organizations enabled and active accounts created.")
        st.stop()
    
    st.info(f"✅ Found {len(all_accounts)} active account(s)")
    
except Exception as e:
    st.error(f"❌ Error loading accounts: {str(e)}")
    st.info("""
    Ensure your management account has Organizations permissions:
    - organizations:ListAccounts
    - organizations:DescribeOrganization
    """)
    st.stop()

# Store accounts in session state for use in pages
st.session_state.accounts = all_accounts

# Main content area
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Available Dashboards")
    st.markdown("""
    - **EC2 Details**: Monitor EC2 instances across accounts and regions
    - **Security Hub**: View security findings and compliance status
    - **AWS Config**: Track configuration compliance and rules
    - **IAM Key Rotation**: Monitor access key age and rotation status
    - **VPC Details**: View VPC configurations (template)
    - **Backup Details**: Track backup status (template)
    
    Select a dashboard from the navigation menu to get started.
    """)

with col2:
    st.subheader("🚀 Features")
    st.markdown("""
    - **Multi-account support**: Scan resources across all AWS accounts
    - **Cross-region discovery**: Find resources in all AWS regions
    - **Real-time filtering**: Filter results by multiple criteria
    - **CSV export**: Download results for further analysis
    - **Session persistence**: Maintains selections across page refreshes
    - **Secure access**: Uses STS AssumeRole for cross-account access
    """)

# Quick Stats
st.markdown("---")
st.subheader("📈 Organization Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Accounts", len(all_accounts))

with col2:
    active_accounts = len([acc for acc in all_accounts if acc['Status'] == 'ACTIVE'])
    st.metric("Active Accounts", active_accounts)

with col3:
    st.metric("Management Account", account_id)

with col4:
    st.metric("Dashboard Pages", "6")

# Getting Started Guide
st.markdown("---")
with st.expander("🎯 Getting Started Guide"):
    st.markdown("""
    ### How to Use This Dashboard
    
    1. **Select a Dashboard** from the sidebar navigation
    2. **Choose Account(s)** to scan (one or multiple)
    3. **Select Region(s)** to search (common, all, or custom)
    4. **Click "Fetch" Button** to retrieve data
    5. **Use Filters** to narrow down results
    6. **Download CSV** for offline analysis
    
    ### Keyboard Shortcuts
    - `Ctrl/Cmd + S` - Sidebar toggle
    - `Ctrl/Cmd + R` - Refresh page
    
    ### Tips
    - Use "Common Regions" mode for faster scans
    - Select specific accounts to reduce API calls
    - Clear data before switching between dashboards
    - Use "Refresh Data" button to update existing data
    
    ### Prerequisites
    - AWS credentials configured (profile or environment variables)
    - IAM roles created in member accounts with name: `{AWSConfig.READONLY_ROLE_NAME}`
    - Trust relationship established between management and member accounts
    """)

# Footer
st.markdown("---")
st.caption(f"""
AWS Multi-Account Dashboard | Powered by Streamlit & Boto3 | 🔒 Secure Multi-Account Access
Configuration: Profile={AWSConfig.MANAGEMENT_ACCOUNT_PROFILE} | Role={AWSConfig.READONLY_ROLE_NAME} | Workers={AWSConfig.MAX_WORKERS}
""")
```
