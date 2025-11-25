"""
IAM Users Dashboard - With Color-Coded Key Ages

Uses your utils.py with proper data handling.
Key age color coding: 🟢 Good (<60d), 🟡 Warning (60-90d), 🔴 Critical (>90d)
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

# Sidebar
account_ids, regions = setup_account_filter(page_key="iam")

st.sidebar.markdown("---")
st.sidebar.subheader("⏰ Key Age Thresholds")
warning_days = st.sidebar.number_input("Warning (days):", min_value=1, value=60)
critical_days = st.sidebar.number_input("Critical (days):", min_value=1, value=90)

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

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

def get_key_age_status(age_days, warning, critical):
    """Get color-coded status for key age"""
    if age_days <= warning:
        return "🟢 Good", "green"
    elif age_days <= critical:
        return "🟡 Warning", "orange"
    else:
        return "🔴 Critical", "red"

def get_iam_users(account_id, account_name, role_name, warning_days, critical_days):
    """Get IAM users and their details"""
    users_data = []
    errors = []
    
    try:
        iam_client = get_iam_client(account_id, role_name)
        if not iam_client:
            errors.append(f"❌ {account_name}: Failed to get IAM client")
            return users_data, errors
        
        # Test connection
        try:
            iam_client.get_account_summary()
        except ClientError as e:
            errors.append(f"❌ {account_name}: Cannot access IAM - {str(e)}")
            return users_data, errors
        
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
                            status_text, status_color = get_key_age_status(key_age, warning_days, critical_days)
                            
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
                            
                            users_data.append({
                                'Account ID': account_id,
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
                                'Status Color': status_color,
                                'Key Last Used': last_used,
                                'Days Since Used': days_since_used,
                                'Last Service': last_service
                            })
                    else:
                        users_data.append({
                            'Account ID': account_id,
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
                            'Status Color': 'gray',
                            'Key Last Used': 'N/A',
                            'Days Since Used': 'N/A',
                            'Last Service': 'N/A'
                        })
                except ClientError as e:
                    errors.append(f"⚠️ {account_name}/{username}: Cannot list keys - {str(e)}")
        
        if user_count == 0:
            errors.append(f"ℹ️ {account_name}: No IAM users found")
                
    except Exception as e:
        errors.append(f"❌ {account_name}: Unexpected error - {str(e)}")
    
    return users_data, errors

def fetch_data(account_ids, all_accounts, role_name, warning_days, critical_days):
    """Fetch data with parallel processing"""
    all_data = []
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(account_ids)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_account = {
            executor.submit(get_iam_users, account_id,
                          get_account_name_by_id(account_id, all_accounts),
                          role_name, warning_days, critical_days): account_id
            for account_id in account_ids
        }
        
        for future in as_completed(future_to_account):
            account_id = future_to_account[future]
            account_name = get_account_name_by_id(account_id, all_accounts)
            completed += 1
            status_text.text(f"📡 {account_name} ({completed}/{total})")
            progress_bar.progress(completed / total)
            
            try:
                data, errors = future.result()
                all_data.extend(data)
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"❌ {account_name}: Failed - {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return all_data, all_errors

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
            data, errors = fetch_data(account_ids, all_accounts, "readonly-role", warning_days, critical_days)
            st.session_state.iam_data = data
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
                data, errors = fetch_data(account_ids, all_accounts, "readonly-role", warning_days, critical_days)
                st.session_state.iam_data = data
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
        
        # Data table with color coding
        st.subheader(f"📋 IAM Users ({len(filtered)} records)")
        
        # Apply color styling
        def highlight_key_age(row):
            color = row['Status Color']
            if color == 'red':
                return ['background-color: #ffcccc'] * len(row)
            elif color == 'orange':
                return ['background-color: #ffe6cc'] * len(row)
            elif color == 'green':
                return ['background-color: #ccffcc'] * len(row)
            else:
                return [''] * len(row)
        
        # Display columns
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
        st.caption(f"🟢 Good (≤{warning_days} days) | 🟡 Warning ({warning_days+1}-{critical_days} days) | 🔴 Critical (>{critical_days} days)")
        
        # Download
        st.markdown("---")
        csv = filtered.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"iam_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

else:
    st.info("👈 Select accounts, then click 'Fetch Data'")
