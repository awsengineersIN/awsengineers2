"""
Lambda Dashboard - Enhanced with Graphs

Features:
- Filter by account and region
- View Lambda functions with detailed information
- Overview with graphs and charts
- Runtime distribution pie chart
- Memory usage distribution
- Timeout distribution
- Function count by account/region
- Table showing all Lambda details
- CSV export

Uses your utils.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import boto3
import plotly.express as px

from utils import (
    assume_role,
    setup_account_filter,
    get_account_name_by_id,
)
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(page_title="Lambda", page_icon="⚡", layout="wide")

# Initialize session state
if 'lambda_data' not in st.session_state:
    st.session_state.lambda_data = None
if 'lambda_last_refresh' not in st.session_state:
    st.session_state.lambda_last_refresh = None
if 'lambda_errors' not in st.session_state:
    st.session_state.lambda_errors = []

st.title("⚡ Lambda Functions Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="lambda")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_lambda_client(account_id, role_name, region):
    """Get Lambda client"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'lambda',
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_lambda_functions(account_id, account_name, region, role_name):
    """Get Lambda functions for an account/region"""
    functions = []
    errors = []
    
    try:
        lambda_client = get_lambda_client(account_id, role_name, region)
        if not lambda_client:
            errors.append(f"❌ {account_name}/{region}: Failed to get Lambda client")
            return functions, errors
        
        # List functions
        paginator = lambda_client.get_paginator('list_functions')
        
        for page in paginator.paginate():
            for func in page['Functions']:
                last_modified = func.get('LastModified', 'N/A')
                if isinstance(last_modified, str):
                    try:
                        last_modified = datetime.fromisoformat(last_modified.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                functions.append({
                    'Account Name': account_name,
                    'Account ID': account_id,
                    'Region': region,
                    'Function Name': func['FunctionName'],
                    'Function ARN': func['FunctionArn'],
                    'Runtime': func.get('Runtime', 'N/A'),
                    'Memory (MB)': func.get('MemorySize', 0),
                    'Timeout (s)': func.get('Timeout', 0),
                    'Handler': func.get('Handler', 'N/A'),
                    'Last Modified': last_modified,
                    'State': func.get('State', 'N/A'),
                    'Code Size (Bytes)': func.get('CodeSize', 0),
                    'Ephemeral Storage (MB)': func.get('EphemeralStorage', {}).get('Size', 512)
                })
    
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return functions, errors

def fetch_data(account_ids, all_accounts, regions, role_name):
    """Fetch Lambda data with parallel processing"""
    all_data = []
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(account_ids) * len(regions)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        
        for account_id in account_ids:
            account_name = get_account_name_by_id(account_id, all_accounts)
            for region in regions:
                future = executor.submit(get_lambda_functions, account_id, account_name, region, role_name)
                futures[future] = (account_id, account_name, region)
        
        for future in as_completed(futures):
            account_id, account_name, region = futures[future]
            completed += 1
            status_text.text(f"📡 {account_name}/{region} ({completed}/{total})")
            progress_bar.progress(completed / total)
            
            try:
                data, errors = future.result()
                all_data.extend(data)
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"❌ {account_name}/{region}: Failed - {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return all_data, all_errors

# ============================================================================
# FETCH BUTTON
# ============================================================================

if st.session_state.get('lambda_fetch_clicked', False):
    if not account_ids or not regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.lambda_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning Lambda functions..."):
            data, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
            st.session_state.lambda_data = data
            st.session_state.lambda_errors = errors
            st.session_state.lambda_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if data:
            st.success(f"✅ Found {len(data)} Lambda functions in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No Lambda functions found in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.lambda_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.lambda_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.lambda_errors:
            st.write(error)

if st.session_state.lambda_data is not None:
    df = pd.DataFrame(st.session_state.lambda_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.lambda_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.lambda_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                data, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
                st.session_state.lambda_data = data
                st.session_state.lambda_errors = errors
                st.session_state.lambda_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed ({len(data)} functions in {elapsed:.2f}s)")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df.empty:
        st.info("ℹ️ No Lambda functions found.")
    else:
        # ==================== METRICS ====================
        st.subheader("📊 Summary")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Functions", len(df))
        with col2:
            st.metric("Regions", df['Region'].nunique())
        with col3:
            avg_memory = df['Memory (MB)'].mean()
            st.metric("Avg Memory", f"{avg_memory:.0f} MB")
        with col4:
            avg_timeout = df['Timeout (s)'].mean()
            st.metric("Avg Timeout", f"{avg_timeout:.0f}s")
        with col5:
            runtimes = df['Runtime'].nunique()
            st.metric("Runtimes", runtimes)
        
        st.markdown("---")
        
        # ==================== OVERVIEW GRAPHS ====================
        st.subheader("📈 Overview")
        
        graph_col1, graph_col2 = st.columns(2)
        
        # Runtime Distribution
        with graph_col1:
            runtime_counts = df['Runtime'].value_counts()
            fig_runtime = px.pie(
                values=runtime_counts.values,
                names=runtime_counts.index,
                title="Functions by Runtime",
                hole=0.3
            )
            st.plotly_chart(fig_runtime, use_container_width=True)
        
        # Memory Distribution
        with graph_col2:
            memory_bins = pd.cut(df['Memory (MB)'], bins=[0, 128, 512, 1024, 3008, 10240], 
                                 labels=['≤128MB', '128-512MB', '512-1GB', '1-3GB', '>3GB'])
            memory_counts = memory_bins.value_counts().sort_index()
            fig_memory = px.bar(
                x=memory_counts.index.astype(str),
                y=memory_counts.values,
                title="Memory Distribution",
                labels={'x': 'Memory Range', 'y': 'Count'}
            )
            fig_memory.update_traces(marker_color='#1f77b4')
            st.plotly_chart(fig_memory, use_container_width=True)
        
        graph_col3, graph_col4 = st.columns(2)
        
        # Functions by Account
        with graph_col3:
            account_counts = df['Account Name'].value_counts()
            fig_account = px.bar(
                x=account_counts.index,
                y=account_counts.values,
                title="Functions by Account",
                labels={'x': 'Account', 'y': 'Count'}
            )
            fig_account.update_traces(marker_color='#2ca02c')
            st.plotly_chart(fig_account, use_container_width=True)
        
        # Functions by Region
        with graph_col4:
            region_counts = df['Region'].value_counts()
            fig_region = px.bar(
                x=region_counts.index,
                y=region_counts.values,
                title="Functions by Region",
                labels={'x': 'Region', 'y': 'Count'}
            )
            fig_region.update_traces(marker_color='#ff7f0e')
            st.plotly_chart(fig_region, use_container_width=True)
        
        # Timeout Distribution
        timeout_bins = pd.cut(df['Timeout (s)'], bins=[0, 30, 60, 300, 900], 
                              labels=['<30s', '30-60s', '60-5m', '>5m'])
        timeout_counts = timeout_bins.value_counts().sort_index()
        
        fig_timeout = px.bar(
            x=timeout_counts.index.astype(str),
            y=timeout_counts.values,
            title="Timeout Distribution",
            labels={'x': 'Timeout Range', 'y': 'Count'}
        )
        fig_timeout.update_traces(marker_color='#d62728')
        st.plotly_chart(fig_timeout, use_container_width=True)
        
        st.markdown("---")
        
        # ==================== FILTERS ====================
        st.subheader("🔍 Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            accounts_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique()),
                default=sorted(df['Account Name'].unique())
            )
        
        with col2:
            regions_filter = st.multiselect(
                "Region:",
                options=sorted(df['Region'].unique()),
                default=sorted(df['Region'].unique())
            )
        
        with col3:
            runtime_filter = st.multiselect(
                "Runtime:",
                options=sorted(df['Runtime'].unique()),
                default=sorted(df['Runtime'].unique())
            )
        
        filtered = df[
            (df['Account Name'].isin(accounts_filter)) &
            (df['Region'].isin(regions_filter)) &
            (df['Runtime'].isin(runtime_filter))
        ]
        
        st.markdown("---")
        
        # Data table
        st.subheader(f"📋 Lambda Functions ({len(filtered)} functions)")
        
        display_cols = [
            'Account Name', 'Region', 'Function Name', 'Runtime', 
            'Memory (MB)', 'Timeout (s)', 'Handler', 'Last Modified', 'State'
        ]
        
        display_df = filtered[display_cols]
        st.dataframe(
            display_df,
            use_container_width=True,
            height=500
        )
        
        st.markdown("---")
        
        # Download
        csv = filtered[display_cols].to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"lambda_functions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
