"""
Main Dashboard Page - With Organization Hierarchy Display

Displays AWS Organization structure with OUs and accounts in hierarchical tree view
"""

import streamlit as st
from datetime import datetime
import pandas as pd

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

# Custom CSS for hierarchy display
st.markdown("""
<style>
    .ou-container {
        border-left: 3px solid #1f77b4;
        padding-left: 15px;
        margin-left: 10px;
        margin-top: 5px;
        margin-bottom: 5px;
    }
    .account-container {
        border-left: 3px solid #2ca02c;
        padding-left: 15px;
        margin-left: 20px;
        margin-top: 3px;
        margin-bottom: 3px;
    }
    .root-container {
        border: 2px solid #ff7f0e;
        padding: 15px;
        border-radius: 8px;
        background-color: #fff5e6;
        margin-bottom: 15px;
    }
    .hierarchy-item {
        font-family: monospace;
        padding: 8px;
        margin: 3px 0;
        background-color: #f8f9fa;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

st.title("☁️ AWS Multi-Account Dashboard")

# Initialize session state
if 'accounts' not in st.session_state:
    st.session_state.accounts = []
    with st.spinner("Loading organization..."):
        accounts = get_organization_accounts()
        st.session_state.accounts = accounts

# Sidebar
with st.sidebar:
    st.header("🚀 Dashboard Navigation")
    
    page = st.radio(
        "Select a page:",
        options=[
            "📊 Organization Overview",
            "💰 Billing",
            "🔒 Security Hub",
            "🏥 Account Health",
            "👥 IAM Users",
            "⚙️ AWS Config",
            "🌐 VPC",
            "💾 EBS Volumes"
        ],
        index=0
    )
    
    st.markdown("---")
    
    # Load accounts for dashboard filters
    setup_account_filter(page_key="main")

# ============================================================================
# PAGE: ORGANIZATION OVERVIEW
# ============================================================================

if page == "📊 Organization Overview":
    st.markdown("## 📊 AWS Organization Structure")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("🌳 Organization Hierarchy")
    
    with col2:
        view_mode = st.radio("View:", ["Hierarchy", "Flat List"], horizontal=True)
    
    # Load hierarchy
    with st.spinner("Loading organization hierarchy..."):
        hierarchy = get_organization_hierarchy()
    
    if hierarchy is None:
        st.error("❌ Failed to load organization hierarchy")
    else:
        # ==================== HIERARCHICAL VIEW ====================
        if view_mode == "Hierarchy":
            def render_node(node, level=0):
                """Recursively render hierarchy nodes"""
                indent = "  " * level
                
                if node['Type'] == 'ROOT':
                    st.markdown(f"""
                    <div class="root-container">
                        <div style="font-size: 18px; font-weight: bold;">
                            🏢 {node['Name']} (Root)
                        </div>
                        <div style="font-size: 12px; color: #666;">
                            ID: {node['Id']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Render child OUs
                    for child in node['Children']:
                        render_node(child, level + 1)
                    
                    # Render accounts at root
                    if node['Accounts']:
                        st.markdown(f"<div style='margin-left: {level * 20}px;'><b>Accounts:</b></div>", unsafe_allow_html=True)
                        for account in node['Accounts']:
                            st.markdown(f"""
                            <div class="account-container" style="margin-left: {(level + 1) * 20}px;">
                                <div style="font-weight: 500;">📌 {account['Name']}</div>
                                <div style="font-size: 12px; color: #666;">
                                    ID: {account['Id']} | Email: {account['Email']}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                
                elif node['Type'] == 'OU':
                    st.markdown(f"""
                    <div style="margin-left: {level * 20}px;">
                        <div class="hierarchy-item" style="border-left: 4px solid #1f77b4;">
                            <div style="font-weight: 600; font-size: 14px;">📁 {node['Name']}</div>
                            <div style="font-size: 11px; color: #666;">OU ID: {node['Id']}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Render child OUs
                    for child in node['Children']:
                        render_node(child, level + 1)
                    
                    # Render accounts in this OU
                    if node['Accounts']:
                        for account in node['Accounts']:
                            st.markdown(f"""
                            <div class="account-container" style="margin-left: {(level + 1) * 20}px;">
                                <div style="font-weight: 500;">📌 {account['Name']}</div>
                                <div style="font-size: 12px; color: #666;">
                                    ID: {account['Id']} | Email: {account['Email']}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
            
            render_node(hierarchy)
        
        # ==================== FLAT LIST VIEW ====================
        else:
            st.subheader("📋 All Accounts")
            
            def flatten_accounts(node, parent_ou="Root"):
                """Flatten hierarchy to list of accounts with their OUs"""
                accounts_list = []
                
                # Add accounts from this node
                for account in node['Accounts']:
                    accounts_list.append({
                        'Account Name': account['Name'],
                        'Account ID': account['Id'],
                        'Email': account['Email'],
                        'Organizational Unit': parent_ou,
                        'Status': account['Status']
                    })
                
                # Add accounts from child OUs
                for child in node['Children']:
                    accounts_list.extend(flatten_accounts(child, f"{parent_ou} → {child['Name']}"))
                
                return accounts_list
            
            flat_accounts = flatten_accounts(hierarchy)
            df_accounts = pd.DataFrame(flat_accounts)
            
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.metric("Total Accounts", len(df_accounts))
            with col2:
                st.metric("Total OUs", hierarchy['Children'].__len__())
            with col3:
                st.metric("Last Updated", datetime.now().strftime('%Y-%m-%d %H:%M'))
            
            st.markdown("---")
            
            st.dataframe(df_accounts, use_container_width=True, hide_index=True)
            
            # Download button
            csv = df_accounts.to_csv(index=False)
            st.download_button(
                label="📥 Download Accounts CSV",
                data=csv,
                file_name=f"organization_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
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

# ============================================================================
# OTHER PAGES - ROUTE TO DASHBOARD PAGES
# ============================================================================

elif page == "💰 Billing":
    st.info("👈 Navigate to 'Billing' page from sidebar")

elif page == "🔒 Security Hub":
    st.info("👈 Navigate to 'Security Hub' page from sidebar")

elif page == "🏥 Account Health":
    st.info("👈 Navigate to 'Account Health' page from sidebar")

elif page == "👥 IAM Users":
    st.info("👈 Navigate to 'IAM Users' page from sidebar")

elif page == "⚙️ AWS Config":
    st.info("👈 Navigate to 'AWS Config' page from sidebar")

elif page == "🌐 VPC":
    st.info("👈 Navigate to 'VPC' page from sidebar")

elif page == "💾 EBS Volumes":
    st.info("👈 Navigate to 'EBS Volumes' page from sidebar")

# Footer
st.markdown("---")
st.caption(f"🔄 Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Dashboard Version: 2.0")
