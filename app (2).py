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

# Load hierarchy
with st.spinner("Loading organization hierarchy..."):
    hierarchy = get_organization_hierarchy()

if hierarchy is None:
    st.error("❌ Failed to load organization hierarchy")
else:
    # ==================== STATISTICS ====================
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
    
    st.markdown("---")
    
    # ==================== TREE HIERARCHICAL VIEW ====================
    with st.expander("🌳 View Organization Hierarchy", expanded=False):
        def render_node(node):
            """Recursively render hierarchy nodes with tree structure"""
            
            if node['Type'] == 'ROOT':
                st.write(f"🏢 **{node['Name']}** (Root)")
                
                # Process children and accounts
                all_items = []
                
                # Add child OUs
                for child in node['Children']:
                    all_items.append(('OU', child))
                
                # Add accounts at root
                for account in node['Accounts']:
                    all_items.append(('ACCOUNT', account))
                
                # Render all items
                for idx, (item_type, item) in enumerate(all_items):
                    is_last = idx == len(all_items) - 1
                    if item_type == 'OU':
                        render_ou(item, "", is_last)
                    else:
                        render_account(item, "", is_last)
        
        def render_ou(ou, prefix="", is_last=True):
            """Render OU node"""
            connector = "└── " if is_last else "├── "
            next_prefix = prefix + ("    " if is_last else "│   ")
            
            st.write(f"{prefix}{connector}📁 **{ou['Name']}**")
            
            # Process child OUs and accounts
            all_items = []
            
            # Add child OUs
            for child in ou['Children']:
                all_items.append(('OU', child))
            
            # Add accounts in this OU
            for account in ou['Accounts']:
                all_items.append(('ACCOUNT', account))
            
            # Render all items
            for idx, (item_type, item) in enumerate(all_items):
                is_last_item = idx == len(all_items) - 1
                if item_type == 'OU':
                    render_ou(item, next_prefix, is_last_item)
                else:
                    render_account(item, next_prefix, is_last_item)
        
        def render_account(account, prefix="", is_last=True):
            """Render account node"""
            connector = "└── " if is_last else "├── "
            
            st.write(f"{prefix}{connector}👤 **{account['Name']}** ({account['Email']})")
        
        st.write("")
        render_node(hierarchy)

# Footer
st.markdown("---")
st.caption(f"🔄 Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Dashboard Version: 2.0")
