"""
[SERVICE NAME] Dashboard - Simplified Template

INSTRUCTIONS:
1. Replace [SERVICE NAME] with your service (e.g., "RDS Instances")
2. Replace [service] with lowercase service name (e.g., "rds")
3. Implement get_service_data_in_region() function
4. Done!
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from modules.aws_helper import AWSConfig, AWSOrganizations, AWSSession
from modules.sidebar_common import render_sidebar
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(page_title="[SERVICE NAME]", page_icon="📊", layout="wide")

# Initialize session state
if '[service]_data' not in st.session_state:
    st.session_state.[service]_data = None
if '[service]_last_refresh' not in st.session_state:
    st.session_state.[service]_last_refresh = None
if '[service]_errors' not in st.session_state:
    st.session_state.[service]_errors = []

# Header
st.title("📊 [SERVICE NAME] Dashboard")

# Get all accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
selected_account_ids, selected_regions = render_sidebar(page_key_prefix="[service]_")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# TODO: IMPLEMENT THIS FUNCTION
# ============================================================================

def get_service_data_in_region(region, account_id, account_name, role_name):
    """
    Get service data for a specific region.
    
    TODO: Replace this with your service-specific logic.
    """
    data_items = []
    errors = []
    
    try:
        # Get service client
        client = AWSSession.get_client_for_account('[service]', account_id, role_name, region)
        
        # Fetch data with pagination
        # Example:
        # paginator = client.get_paginator('describe_[resources]')
        # for page in paginator.paginate():
        #     for item in page['[Items]']:
        #         data_items.append({
        #             'Account ID': account_id,
        #             'Account Name': account_name,
        #             'Region': region,
        #             'Resource ID': item['[IdKey]'],
        #             'Name': item.get('[NameKey]', 'N/A'),
        #             # Add more fields...
        #         })
        
        # Placeholder - remove when implementing
        errors.append(f"ℹ️ {account_name}/{region}: TODO - Implement data fetching")
                    
    except ClientError as e:
        errors.append(f"⚠️ {account_name}/{region}: Cannot access service - {str(e)}")
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return data_items, errors

# ============================================================================
# PARALLEL FETCH (No changes needed)
# ============================================================================

def fetch_service_data(selected_account_ids, all_accounts, role_name, regions):
    """Fetch service data - optimized parallel processing"""
    all_data = []
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with ThreadPoolExecutor(max_workers=AWSConfig.MAX_WORKERS) as executor:
        futures = {}
        
        for account_id in selected_account_ids:
            account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
            for region in regions:
                future = executor.submit(get_service_data_in_region, region, account_id, account_name, role_name)
                futures[future] = (account_id, account_name, region)
        
        total_tasks = len(futures)
        completed = 0
        
        for future in as_completed(futures):
            account_id, account_name, region = futures[future]
            completed += 1
            
            status_text.text(f"📡 {account_name} / {region} ({completed}/{total_tasks})")
            progress_bar.progress(completed / total_tasks)
            
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

if st.session_state.get('[service]_fetch_clicked', False):
    if not selected_account_ids or not selected_regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.[service]_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning..."):
            data, errors = fetch_service_data(selected_account_ids, all_accounts, AWSConfig.READONLY_ROLE_NAME, selected_regions)
            st.session_state.[service]_data = data
            st.session_state.[service]_errors = errors
            st.session_state.[service]_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if data:
            st.success(f"✅ Found {len(data)} items in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No data found in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.[service]_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.[service]_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.[service]_errors:
            st.write(error)

if st.session_state.[service]_data is not None:
    df = pd.DataFrame(st.session_state.[service]_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.[service]_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.[service]_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                data, errors = fetch_service_data(selected_account_ids, all_accounts, AWSConfig.READONLY_ROLE_NAME, selected_regions)
                st.session_state.[service]_data = data
                st.session_state.[service]_errors = errors
                st.session_state.[service]_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed ({len(data)} items in {elapsed:.2f}s)")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df.empty:
        st.info("ℹ️ No data found.")
    else:
        # Metrics
        st.subheader("📊 Summary")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Items", len(df))
        with col2:
            st.metric("Accounts", df['Account ID'].nunique())
        with col3:
            st.metric("Regions", df['Region'].nunique())
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        col1, col2 = st.columns(2)
        
        with col1:
            regions = st.multiselect(
                "Region:",
                options=sorted(df['Region'].unique()),
                default=sorted(df['Region'].unique())
            )
        
        with col2:
            accounts = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique()),
                default=sorted(df['Account Name'].unique())
            )
        
        filtered = df[(df['Region'].isin(regions)) & (df['Account Name'].isin(accounts))]
        
        st.markdown("---")
        
        # Data table
        st.subheader(f"📋 Data ({len(filtered)} items)")
        st.dataframe(filtered, use_container_width=True, height=500, hide_index=True)
        
        # Download
        st.markdown("---")
        csv = filtered.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"[service]_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
