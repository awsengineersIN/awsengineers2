"""
IAM Users Dashboard - With Navigation Support (Metadata Lookup)

Key age thresholds hardcoded:
- 🟢 Good: ≤60 days
- 🟡 Warning: 61-90 days
- 🔴 Critical: >90 days

Uses metadata dictionary for navigation without displaying Account ID/Region in table

Uses your utils.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import boto3

from utils import (
    assume_role,
    setup_account_filter,
    get_account_name_by_id,
)
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(page_title="IAM Users", page_icon="👥", layout="wide")

# Initialize session state
if 'iam_data' not in st.session_state:
    st.session_state.iam_data = None
if 'iam_metadata' not in st.session_state:
    st.session_state.iam_metadata = {}
if 'iam_last_refresh' not in st.session_state:
    st.session_state.iam_last_refresh = None
if 'iam_errors' not in st.session_state:
    st.session_state.iam_errors = []

st.title("👥 IAM Users Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar (no thresholds - hardcoded in code)
account_ids, regions = setup_account_filter(page_key="iam")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# Hardcoded thresholds
WARNING_DAYS = 60
CRITICAL_DAYS = 90

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_iam_client(account_id, role_name):
    """Get IAM client using your assume_role function"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'iam',
        region_name='us-east-1',  # IAM is global
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_key_age_status(age_days):
    """Get color-coded status for key age - hardcoded thresholds"""
    if age_days <= WARNING_DAYS:
        return "🟢 Good"
    elif age_days <= CRITICAL_DAYS:
        return "🟡 Warning"
    else:
        return "🔴 Critical"

def get_iam_users(account_id, account_name, role_name):
    """Get IAM users and their details - Returns display data + metadata"""
    users_data = []
    metadata = {}
    errors = []
    
    try:
        iam_client = get_iam_client(account_id, role_name)
        if not iam_client:
            errors.append(f"❌ {account_name}: Failed to get IAM client")
            return users_data, metadata, errors
        
        # Test connection
        try:
            iam_client.get_account_summary()
        except ClientError as e:
            errors.append(f"❌ {account_name}: Cannot access IAM - {str(e)}")
            return users_data, metadata, errors
        
        # List users
        paginator = iam_client.get_paginator('list_users')
        user_count = 0
        
        for page in paginator.paginate():
            for user in page['Users']:
                user_count += 1
                username = user['UserName']
                user_arn = user['Arn']
                create_date = user['CreateDate']
                user_age = (datetime.now(create_date.tzinfo) - create_date).days
                
                password_last_used = user.get('PasswordLastUsed', None)
                if password_last_used:
                    password_last_used = password_last_used.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    password_last_used = 'Never'
                
                # Check MFA
                mfa_enabled = "❌ No"
                try:
                    mfa_response = iam_client.list_mfa_devices(UserName=username)
                    if len(mfa_response['MFADevices']) > 0:
                        mfa_enabled = "✅ Yes"
                except:
                    pass
                
                # Get access keys
                try:
                    keys_response = iam_client.list_access_keys(UserName=username)
                    access_keys = keys_response['AccessKeyMetadata']
                    
                    if access_keys:
                        for key in access_keys:
                            key_id = key['AccessKeyId']
                            key_create = key['CreateDate']
                            key_status = key['Status']
                            key_age = (datetime.now(key_create.tzinfo) - key_create).days
                            
                            # Get color-coded status
                            status_text = get_key_age_status(key_age)
                            
                            # Get last used info
                            last_used = "Never"
                            last_service = "N/A"
                            days_since_used = "N/A"
                            
                            try:
                                last_used_resp = iam_client.get_access_key_last_used(AccessKeyId=key_id)
                                if 'LastUsedDate' in last_used_resp.get('AccessKeyLastUsed', {}):
                                    last_date = last_used_resp['AccessKeyLastUsed']['LastUsedDate']
                                    last_used = last_date.strftime('%Y-%m-%d %H:%M:%S')
                                    last_service = last_used_resp['AccessKeyLastUsed'].get('ServiceName', 'N/A')
                                    days_since_used = (datetime.now(last_date.tzinfo) - last_date).days
                            except:
                                pass
                            
                            # Create unique key for metadata lookup
                            record_key = f"{account_id}|{username}|{key_id}"
                            
                            # Display data (without Account ID/Region)
                            users_data.append({
                                'Record Key': record_key,  # Hidden unique identifier
                                'Account Name': account_name,
                                'User Name': username,
                                'User ARN': user_arn,
                                'User Age (Days)': user_age,
                                'Password Last Used': password_last_used,
                                'MFA Enabled': mfa_enabled,
                                'Access Key ID': key_id,
                                'Key Status': key_status,
                                'Key Age (Days)': key_age,
                                'Key Age Status': status_text,
                                'Key Last Used': last_used,
                                'Days Since Used': days_since_used,
                                'Last Service': last_service
                            })
                            
                            # Metadata for navigation (stored separately)
                            metadata[record_key] = {
                                'account_id': account_id,
                                'account_name': account_name,
                                'region': 'us-east-1',  # IAM is global
                                'username': username,
                                'user_arn': user_arn,
                                'key_id': key_id
                            }
                    else:
                        # User with no keys
                        record_key = f"{account_id}|{username}|NO_KEY"
                        
                        users_data.append({
                            'Record Key': record_key,
                            'Account Name': account_name,
                            'User Name': username,
                            'User ARN': user_arn,
                            'User Age (Days)': user_age,
                            'Password Last Used': password_last_used,
                            'MFA Enabled': mfa_enabled,
                            'Access Key ID': 'No Keys',
                            'Key Status': 'N/A',
                            'Key Age (Days)': 0,
                            'Key Age Status': 'N/A',
                            'Key Last Used': 'N/A',
                            'Days Since Used': 'N/A',
                            'Last Service': 'N/A'
                        })
                        
                        metadata[record_key] = {
                            'account_id': account_id,
                            'account_name': account_name,
                            'region': 'us-east-1',
                            'username': username,
                            'user_arn': user_arn,
                            'key_id': None
                        }
                except ClientError as e:
                    errors.append(f"⚠️ {account_name}/{username}: Cannot list keys - {str(e)}")
        
        if user_count == 0:
            errors.append(f"ℹ️ {account_name}: No IAM users found")
                
    except Exception as e:
        errors.append(f"❌ {account_name}: Unexpected error - {str(e)}")
    
    return users_data, metadata, errors

def fetch_data(account_ids, all_accounts, role_name):
    """Fetch data with parallel processing"""
    all_data = []
    all_metadata = {}
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(account_ids)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_account = {
            executor.submit(get_iam_users, account_id,
                          get_account_name_by_id(account_id, all_accounts),
                          role_name): account_id
            for account_id in account_ids
        }
        
        for future in as_completed(future_to_account):
            account_id = future_to_account[future]
            account_name = get_account_name_by_id(account_id, all_accounts)
            completed += 1
            status_text.text(f"📡 {account_name} ({completed}/{total})")
            progress_bar.progress(completed / total)
            
            try:
                data, metadata, errors = future.result()
                all_data.extend(data)
                all_metadata.update(metadata)
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"❌ {account_name}: Failed - {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return all_data, all_metadata, all_errors

# ============================================================================
# FETCH BUTTON
# ============================================================================

if st.session_state.get('iam_fetch_clicked', False):
    if not account_ids:
        st.warning("⚠️ Please select at least one account.")
        st.session_state.iam_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning IAM users..."):
            data, metadata, errors = fetch_data(account_ids, all_accounts, "readonly-role")
            st.session_state.iam_data = data
            st.session_state.iam_metadata = metadata
            st.session_state.iam_errors = errors
            st.session_state.iam_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if data:
            st.success(f"✅ Found {len(data)} user records in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No IAM users in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.iam_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.iam_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.iam_errors:
            st.write(error)

if st.session_state.iam_data is not None:
    df = pd.DataFrame(st.session_state.iam_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.iam_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.iam_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                data, metadata, errors = fetch_data(account_ids, all_accounts, "readonly-role")
                st.session_state.iam_data = data
                st.session_state.iam_metadata = metadata
                st.session_state.iam_errors = errors
                st.session_state.iam_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed ({len(data)} records in {elapsed:.2f}s)")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df.empty:
        st.info("ℹ️ No IAM users found.")
    else:
        # Metrics
        st.subheader("📊 Summary")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Users", df['User Name'].nunique())
        with col2:
            total_keys = len(df[df['Access Key ID'] != 'No Keys'])
            st.metric("🔑 Total Keys", total_keys)
        with col3:
            critical = len(df[df['Key Age Status'] == '🔴 Critical'])
            st.metric("🔴 Critical Keys", critical)
        with col4:
            warning = len(df[df['Key Age Status'] == '🟡 Warning'])
            st.metric("🟡 Warning Keys", warning)
        with col5:
            no_mfa = len(df[df['MFA Enabled'] == '❌ No']['User Name'].unique())
            st.metric("❌ No MFA", no_mfa)
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            accounts_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique()),
                default=sorted(df['Account Name'].unique())
            )
        
        with col2:
            status_filter = st.multiselect(
                "Key Age Status:",
                options=sorted(df['Key Age Status'].unique()),
                default=sorted(df['Key Age Status'].unique())
            )
        
        with col3:
            key_status_filter = st.multiselect(
                "Key Status:",
                options=sorted(df['Key Status'].unique()),
                default=sorted(df['Key Status'].unique())
            )
        
        filtered = df[
            (df['Account Name'].isin(accounts_filter)) &
            (df['Key Age Status'].isin(status_filter)) &
            (df['Key Status'].isin(key_status_filter))
        ]
        
        st.markdown("---")
        
        # Data table with color coding (without Record Key, Account ID, Region)
        st.subheader(f"📋 IAM Users ({len(filtered)} records)")
        
        # Apply color styling based on Key Age Status column
        def highlight_key_age(row):
            status = row['Key Age Status']
            if status == '🔴 Critical':
                return ['background-color: #ffcccc'] * len(row)
            elif status == '🟡 Warning':
                return ['background-color: #ffe6cc'] * len(row)
            elif status == '🟢 Good':
                return ['background-color: #ccffcc'] * len(row)
            else:
                return [''] * len(row)
        
        # Display columns (exclude Record Key, Account ID, Region)
        display_cols = [
            'Account Name', 'User Name', 'User Age (Days)', 'MFA Enabled',
            'Access Key ID', 'Key Status', 'Key Age (Days)', 'Key Age Status',
            'Days Since Used', 'Last Service'
        ]
        
        display_df = filtered[display_cols]
        st.dataframe(
            display_df.style.apply(highlight_key_age, axis=1),
            use_container_width=True,
            height=500
        )
        
        # Legend
        st.caption(f"🟢 Good (≤{WARNING_DAYS} days) | 🟡 Warning ({WARNING_DAYS+1}-{CRITICAL_DAYS} days) | 🔴 Critical (>{CRITICAL_DAYS} days)")
        
        st.markdown("---")
        
        # ============================================================================
        # NAVIGATION: Select user/key for details
        # ============================================================================
        
        st.subheader("🔍 View User Details")
        
        # Create selection options
        user_options = filtered.apply(
            lambda row: f"{row['User Name']} | {row['Account Name']} | Key: {row['Access Key ID']}", 
            axis=1
        ).tolist()
        
        if user_options:
            col1, col2 = st.columns([4, 1])
            
            with col1:
                selected_index = st.selectbox(
                    "Select a user to view detailed information:",
                    options=range(len(user_options)),
                    format_func=lambda x: user_options[x]
                )
            
            with col2:
                st.write("")  # Spacing
                st.write("")  # Spacing
                if st.button("View Details →", type="primary", use_container_width=True):
                    # Get selected row
                    selected_row = filtered.iloc[selected_index]
                    record_key = selected_row['Record Key']
                    
                    # Lookup metadata using record key
                    if record_key in st.session_state.iam_metadata:
                        meta = st.session_state.iam_metadata[record_key]
                        
                        # Store navigation parameters in session state
                        st.session_state.selected_iam_user = meta['username']
                        st.session_state.selected_iam_account_id = meta['account_id']
                        st.session_state.selected_iam_account_name = meta['account_name']
                        st.session_state.selected_iam_region = meta['region']
                        st.session_state.selected_iam_key_id = meta['key_id']
                        st.session_state.selected_iam_user_arn = meta['user_arn']
                        
                        # Navigate to details page (you'll need to create this page)
                        st.info("✅ User details stored. Navigate to IAM User Details page to view.")
                        st.write("**Selected User Information:**")
                        st.write(f"- User: {meta['username']}")
                        st.write(f"- Account: {meta['account_name']}")
                        st.write(f"- Key ID: {meta['key_id'] if meta['key_id'] else 'No Key'}")
                        
                        # Uncomment when you create the IAM_User_Details.py page:
                        # st.switch_page("pages/IAM_User_Details.py")
                    else:
                        st.error("❌ Could not find metadata for selected user")
        
        # Download
        st.markdown("---")
        csv = filtered[display_cols].to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"iam_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # Debug: Show metadata structure
        if debug_mode:
            with st.expander("🔧 Metadata Debug Info"):
                st.write(f"Total metadata records: {len(st.session_state.iam_metadata)}")
                st.write("Sample metadata structure:")
                if st.session_state.iam_metadata:
                    sample_key = list(st.session_state.iam_metadata.keys())[0]
                    st.json({sample_key: st.session_state.iam_metadata[sample_key]})

else:
    st.info("👈 Select accounts, then click 'Fetch Data'")
