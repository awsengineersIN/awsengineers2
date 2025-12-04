"""
Main Dashboard Page - With Organization Hierarchy Display

Displays AWS Organization structure with OUs and accounts in tree view format
"""

import streamlit as st
from datetime import datetime

# Import the updated utils with hierarchy support
# Make sure you replace your utils.py with the updated version
from utils import (
    get_organization_accounts,
    get_organization_hierarchy,
    setup_account_filter,
)

# Page configuration
st.set_page_config(
    page_title="AWS Dashboard",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("☁️ AWS Multi-Account Dashboard")

# Initialize session state
if 'accounts' not in st.session_state:
    st.session_state.accounts = []
    with st.spinner("Loading organization..."):
        accounts = get_organization_accounts()
        st.session_state.accounts = accounts

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Load accounts for dashboard filters
    setup_account_filter(page_key="main")

# ============================================================================
# PAGE: ORGANIZATION OVERVIEW
# ============================================================================

st.markdown("## 📊 AWS Organization Structure")

st.subheader("🌳 Organization Hierarchy")

# Load hierarchy
with st.spinner("Loading organization hierarchy..."):
    hierarchy = get_organization_hierarchy()

if hierarchy is None:
    st.error("❌ Failed to load organization hierarchy")
else:
    # ==================== TREE HIERARCHICAL VIEW ====================
    def render_node(node, prefix="", is_last=True, is_root=True):
        """Recursively render hierarchy nodes with tree structure"""
        
        # Determine the connector
        connector = "└── " if is_last else "├── "
        continuation = "    " if is_last else "│   "
        
        if node['Type'] == 'ROOT':
            st.write(f"🏢 **{node['Name']}** (Root)")
            
            # Process children and accounts
            all_items = []
            
            # Add child OUs
            for i, child in enumerate(node['Children']):
                all_items.append(('OU', child, i == len(node['Children']) - 1 and len(node['Accounts']) == 0))
            
            # Add accounts at root
            for i, account in enumerate(node['Accounts']):
                all_items.append(('ACCOUNT', account, i == len(node['Accounts']) - 1))
            
            # Render all items
            for item_type, item, is_last_item in all_items:
                if item_type == 'OU':
                    render_ou(item, "  ", is_last_item)
                else:
                    render_account(item, "  ", is_last_item)
        
        elif node['Type'] == 'OU':
            render_ou(node, prefix, is_last)
    
    def render_ou(ou, prefix="", is_last=True):
        """Render OU node"""
        connector = "└── " if is_last else "├── "
        continuation = "    " if is_last else "│   "
        
        st.write(f"{prefix}{connector}📁 **{ou['Name']}**")
        
        # Process child OUs and accounts
        all_items = []
        
        # Add child OUs
        for i, child in enumerate(ou['Children']):
            all_items.append(('OU', child, i == len(ou['Children']) - 1 and len(ou['Accounts']) == 0))
        
        # Add accounts in this OU
        for i, account in enumerate(ou['Accounts']):
            all_items.append(('ACCOUNT', account, i == len(ou['Accounts']) - 1))
        
        # Render all items
        for item_type, item, is_last_item in all_items:
            if item_type == 'OU':
                render_ou(item, prefix + continuation, is_last_item)
            else:
                render_account(item, prefix + continuation, is_last_item)
    
    def render_account(account, prefix="", is_last=True):
        """Render account node"""
        connector = "└── " if is_last else "├── "
        
        st.write(f"{prefix}{connector}👤 **{account['Name']}** ({account['Email']})")
    
    render_node(hierarchy)
    
    # ==================== STATISTICS ====================
    st.markdown("---")
    st.subheader("📈 Organization Statistics")
    
    def count_nodes(node):
        """Count OUs and accounts recursively"""
        ou_count = 0 if node['Type'] == 'ROOT' else 1
        account_count = len(node['Accounts'])
        
        for child in node['Children']:
            child_ou_count, child_account_count = count_nodes(child)
            ou_count += child_ou_count
            account_count += child_account_count
        
        return ou_count, account_count
    
    ou_count, total_accounts = count_nodes(hierarchy)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Accounts", total_accounts)
    with col2:
        st.metric("Organizational Units", ou_count)
    with col3:
        st.metric("Root", 1)
    with col4:
        st.metric("Last Sync", datetime.now().strftime('%H:%M'))

# Footer
st.markdown("---")
st.caption(f"🔄 Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Dashboard Version: 2.0")
