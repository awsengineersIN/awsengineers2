# Updated EC2 Details Page (Refresh Data Button Added)

Save this as: `pages/EC2_details.py`

```python
"""
EC2 Details Dashboard Page

Displays EC2 instances across selected accounts and regions.
Uses modular approach with reusable functions from modules/.

Run: streamlit run main.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from modules.config import AWSConfig
from modules.iam import (
    AWSOrganizations, 
    AWSRegions, 
    AWSSession
)
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(page_title="EC2 Details", page_icon="📊", layout="wide")

# Initialize session state
if 'ec2_data' not in st.session_state:
    st.session_state.ec2_data = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = None

# Header
st.title("📊 EC2 Instance Dashboard")

# Sidebar Configuration
st.sidebar.header("⚙️ Configuration")

# Get all accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Account selection
st.sidebar.subheader("📋 Account Selection")
account_options = {f"{acc['Name']} ({acc['Id']})": acc['Id'] for acc in all_accounts}

select_all = st.sidebar.checkbox("Select All Accounts", value=False)

if select_all:
    selected_account_names = list(account_options.keys())
else:
    # Get previously selected account from main page
    default_account = st.session_state.get('selected_account', {}).get('full_name')
    default_idx = 0
    if default_account and default_account in account_options:
        default_idx = list(account_options.keys()).index(default_account)
    
    selected_account_names = st.sidebar.multiselect(
        "Choose Accounts:",
        options=list(account_options.keys()),
        default=[list(account_options.keys())[default_idx]],
        help="Select one or more accounts"
    )

selected_account_ids = [account_options[name] for name in selected_account_names]

# Region selection
st.sidebar.subheader("🌍 Region Selection")
region_mode = st.sidebar.radio(
    "Region Mode:",
    ["Common Regions", "All Regions", "Custom Regions"],
    help="Choose region scanning mode"
)

try:
    if region_mode == "Common Regions":
        selected_regions = AWSRegions.get_common_regions()
        st.sidebar.info(f"Scanning {len(selected_regions)} common regions")
    elif region_mode == "All Regions":
        all_regions = AWSRegions.list_all_regions()
        selected_regions = all_regions
        st.sidebar.info(f"Scanning all {len(all_regions)} regions")
    else:  # Custom Regions
        all_regions = AWSRegions.list_all_regions()
        selected_regions = st.sidebar.multiselect(
            "Select Regions:",
            options=all_regions,
            default=['us-east-1', 'us-west-2']
        )
except Exception as e:
    st.sidebar.error(f"Error loading regions: {str(e)}")
    st.stop()

# Helper functions
def get_ec2_instances_in_region(region, account_id, account_name, role_name):
    """Get EC2 instances for a specific region in a target account"""
    instances = []
    try:
        ec2_client = AWSSession.get_client_for_account(
            'ec2', account_id, role_name, region
        )
        
        paginator = ec2_client.get_paginator('describe_instances')
        
        for page in paginator.paginate():
            for reservation in page['Reservations']:
                for instance in reservation['Instances']:
                    # Extract instance name from tags
                    instance_name = ''
                    if 'Tags' in instance:
                        for tag in instance['Tags']:
                            if tag['Key'] == 'Name':
                                instance_name = tag['Value']
                                break
                    
                    instance_data = {
                        'Account ID': account_id,
                        'Account Name': account_name,
                        'Region': region,
                        'Instance ID': instance['InstanceId'],
                        'Instance Name': instance_name,
                        'Instance Type': instance['InstanceType'],
                        'State': instance['State']['Name'],
                        'Private IP': instance.get('PrivateIpAddress', 'N/A'),
                        'Public IP': instance.get('PublicIpAddress', 'N/A'),
                        'VPC ID': instance.get('VpcId', 'N/A'),
                        'Availability Zone': instance['Placement']['AvailabilityZone'],
                        'Launch Time': instance['LaunchTime'].strftime('%Y-%m-%d %H:%M:%S'),
                        'Platform': instance.get('Platform', 'Linux/Unix'),
                        'Key Name': instance.get('KeyName', 'N/A'),
                        'Monitoring': instance['Monitoring']['State']
                    }
                    instances.append(instance_data)
    except ClientError as e:
        pass  # Region might not be enabled
    except Exception as e:
        pass
    
    return instances

def fetch_ec2_data_for_account(account_id, account_name, role_name, regions):
    """Fetch EC2 data for a specific account across regions"""
    all_instances = []
    
    with ThreadPoolExecutor(max_workers=AWSConfig.MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                get_ec2_instances_in_region, 
                region, 
                account_id, 
                account_name, 
                role_name
            ): region 
            for region in regions
        }
        
        for future in as_completed(futures):
            try:
                instances = future.result()
                all_instances.extend(instances)
            except Exception as e:
                pass
    
    return all_instances

def fetch_all_ec2_data(selected_account_ids, all_accounts, role_name, regions):
    """Fetch EC2 data for all selected accounts"""
    all_ec2_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_accounts = len(selected_account_ids)
    
    for idx, account_id in enumerate(selected_account_ids):
        account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
        
        status_text.text(f"📡 Scanning: {account_name} ({idx + 1}/{total_accounts})")
        
        instances = fetch_ec2_data_for_account(account_id, account_name, role_name, regions)
        all_ec2_data.extend(instances)
        
        progress_bar.progress((idx + 1) / total_accounts)
    
    progress_bar.empty()
    status_text.empty()
    
    return all_ec2_data

# Fetch/Refresh button
st.sidebar.markdown("---")
col1, col2 = st.sidebar.columns(2)

with col1:
    fetch_button = st.button("🔄 Fetch EC2 Instances", type="primary", use_container_width=True)

with col2:
    refresh_button = st.button("🔁 Refresh Data", use_container_width=True)

if fetch_button or refresh_button:
    if not selected_account_ids:
        st.warning("⚠️ Please select at least one account.")
    elif not selected_regions:
        st.warning("⚠️ Please select at least one region.")
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning {len(selected_account_ids)} account(s) across {len(selected_regions)} region(s)..."):
            ec2_data = fetch_all_ec2_data(
                selected_account_ids,
                all_accounts,
                AWSConfig.READONLY_ROLE_NAME,
                selected_regions
            )
            st.session_state.ec2_data = ec2_data
            st.session_state.last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed_time = time.time() - start_time
        st.success(f"✅ Successfully fetched {len(ec2_data)} instances in {elapsed_time:.2f} seconds")

# Clear button
if st.sidebar.button("🗑️ Clear Data", use_container_width=True):
    st.session_state.ec2_data = None
    st.session_state.last_refresh = None
    st.rerun()

# Display results
if st.session_state.last_refresh:
    st.caption(f"Last refreshed: {st.session_state.last_refresh}")

if st.session_state.ec2_data is not None:
    df = pd.DataFrame(st.session_state.ec2_data)
    
    if df.empty:
        st.info("ℹ️ No EC2 instances found in the selected accounts and regions.")
    else:
        # Summary metrics
        st.subheader("📊 Summary Metrics")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Instances", len(df))
        
        with col2:
            running_count = len(df[df['State'] == 'running'])
            st.metric("🟢 Running", running_count)
        
        with col3:
            stopped_count = len(df[df['State'] == 'stopped'])
            st.metric("🔴 Stopped", stopped_count)
        
        with col4:
            unique_accounts = df['Account ID'].nunique()
            st.metric("Accounts", unique_accounts)
        
        with col5:
            unique_regions = df['Region'].nunique()
            st.metric("Regions", unique_regions)
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        
        with filter_col1:
            state_filter = st.multiselect(
                "Instance State:",
                options=sorted(df['State'].unique().tolist()),
                default=sorted(df['State'].unique().tolist())
            )
        
        with filter_col2:
            region_filter = st.multiselect(
                "Region:",
                options=sorted(df['Region'].unique().tolist()),
                default=sorted(df['Region'].unique().tolist())
            )
        
        with filter_col3:
            account_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique().tolist()),
                default=sorted(df['Account Name'].unique().tolist())
            )
        
        with filter_col4:
            instance_type_filter = st.multiselect(
                "Instance Type:",
                options=sorted(df['Instance Type'].unique().tolist()),
                default=sorted(df['Instance Type'].unique().tolist())
            )
        
        # Apply filters
        filtered_df = df[
            (df['State'].isin(state_filter)) &
            (df['Region'].isin(region_filter)) &
            (df['Account Name'].isin(account_filter)) &
            (df['Instance Type'].isin(instance_type_filter))
        ]
        
        st.markdown("---")
        
        # Display data
        st.subheader(f"📋 EC2 Instances ({len(filtered_df)} instances)")
        
        # Column selector
        available_columns = filtered_df.columns.tolist()
        default_columns = [
            'Account Name', 'Region', 'Instance ID', 'Instance Name',
            'Instance Type', 'State', 'Private IP', 'Public IP'
        ]
        
        selected_columns = st.multiselect(
            "Select columns to display:",
            options=available_columns,
            default=[col for col in default_columns if col in available_columns]
        )
        
        if selected_columns:
            display_df = filtered_df[selected_columns]
        else:
            display_df = filtered_df
        
        st.dataframe(display_df, use_container_width=True, height=500, hide_index=True)
        
        # Download section
        st.markdown("---")
        col_download1, col_download2 = st.columns(2)
        
        with col_download1:
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Filtered Data (CSV)",
                data=csv,
                file_name=f"ec2_instances_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_download2:
            all_csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download All Data (CSV)",
                data=all_csv,
                file_name=f"ec2_instances_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        # Statistics
        with st.expander("📈 Additional Statistics"):
            stat_col1, stat_col2 = st.columns(2)
            
            with stat_col1:
                st.write("**Instances by State:**")
                state_counts = filtered_df['State'].value_counts()
                st.dataframe(state_counts, use_container_width=True)
            
            with stat_col2:
                st.write("**Instances by Type:**")
                type_counts = filtered_df['Instance Type'].value_counts().head(10)
                st.dataframe(type_counts, use_container_width=True)

else:
    st.info("👈 Configure options in the sidebar and click 'Fetch EC2 Instances' to begin.")
```
