# IAM Users Dashboard Page

Save this as: `pages/IAM_Users.py`

```python
"""
IAM Users Dashboard Page

Displays IAM users and their access key details including:
- User information (name, ARN, creation date)
- Access keys (age, status, last used)
- MFA status
- Password last used
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
st.set_page_config(page_title="IAM Users", page_icon="👥", layout="wide")

# Initialize session state
if 'iam_users_data' not in st.session_state:
    st.session_state.iam_users_data = None
if 'iam_users_last_refresh' not in st.session_state:
    st.session_state.iam_users_last_refresh = None

# Header
st.title("👥 IAM Users Dashboard")

# Get all accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# ============================================================================
# SIDEBAR CONFIGURATION
# ============================================================================

selected_account_ids, selected_regions = render_sidebar(page_key_prefix="iam_users_")

# Age threshold for highlighting old keys
st.sidebar.markdown("---")
st.sidebar.subheader("⏰ Key Age Threshold")
age_threshold = st.sidebar.number_input(
    "Alert if key age exceeds (days):",
    min_value=1,
    max_value=365,
    value=90,
    help="Keys older than this will be highlighted",
    key="iam_users_threshold"
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_iam_users_for_account(account_id, account_name, role_name, age_threshold):
    """Get IAM users and their details for an account"""
    users_data = []
    try:
        iam_client = AWSSession.get_client_for_account(
            'iam', account_id, role_name, 'us-east-1'  # IAM is global
        )
        
        # List all users
        paginator = iam_client.get_paginator('list_users')
        
        for page in paginator.paginate():
            for user in page['Users']:
                username = user['UserName']
                user_arn = user['Arn']
                user_id = user['UserId']
                create_date = user['CreateDate']
                
                # Calculate user age
                user_age_days = (datetime.now(create_date.tzinfo) - create_date).days
                
                # Get password last used (if available)
                password_last_used = 'Never'
                if 'PasswordLastUsed' in user:
                    password_last_used = user['PasswordLastUsed'].strftime('%Y-%m-%d %H:%M:%S')
                
                # Check MFA status
                mfa_devices = []
                try:
                    mfa_response = iam_client.list_mfa_devices(UserName=username)
                    mfa_devices = mfa_response['MFADevices']
                except:
                    pass
                
                mfa_enabled = "✅ Yes" if len(mfa_devices) > 0 else "❌ No"
                mfa_count = len(mfa_devices)
                
                # Get access keys for this user
                try:
                    keys_response = iam_client.list_access_keys(UserName=username)
                    access_keys = keys_response['AccessKeyMetadata']
                    
                    if access_keys:
                        # Process each key
                        for key in access_keys:
                            access_key_id = key['AccessKeyId']
                            key_create_date = key['CreateDate']
                            key_status = key['Status']
                            
                            # Calculate key age
                            key_age_days = (datetime.now(key_create_date.tzinfo) - key_create_date).days
                            
                            # Determine rotation status
                            if key_age_days > age_threshold:
                                rotation_status = "⚠️ Overdue"
                            elif key_age_days > (age_threshold * 0.8):
                                rotation_status = "⚡ Soon"
                            else:
                                rotation_status = "✅ OK"
                            
                            # Get last used info
                            last_used = "Never"
                            last_used_service = "N/A"
                            last_used_region = "N/A"
                            days_since_used = "N/A"
                            
                            try:
                                last_used_response = iam_client.get_access_key_last_used(
                                    AccessKeyId=access_key_id
                                )
                                if 'LastUsedDate' in last_used_response.get('AccessKeyLastUsed', {}):
                                    last_used_date = last_used_response['AccessKeyLastUsed']['LastUsedDate']
                                    last_used = last_used_date.strftime('%Y-%m-%d %H:%M:%S')
                                    last_used_service = last_used_response['AccessKeyLastUsed'].get('ServiceName', 'N/A')
                                    last_used_region = last_used_response['AccessKeyLastUsed'].get('Region', 'N/A')
                                    
                                    # Calculate days since last used
                                    days_since_used = (datetime.now(last_used_date.tzinfo) - last_used_date).days
                            except:
                                pass
                            
                            user_data = {
                                'Account ID': account_id,
                                'Account Name': account_name,
                                'User Name': username,
                                'User ARN': user_arn,
                                'User ID': user_id,
                                'User Created': create_date.strftime('%Y-%m-%d'),
                                'User Age (Days)': user_age_days,
                                'Password Last Used': password_last_used,
                                'MFA Enabled': mfa_enabled,
                                'MFA Devices': mfa_count,
                                'Access Key ID': access_key_id,
                                'Key Status': key_status,
                                'Key Age (Days)': key_age_days,
                                'Key Rotation Status': rotation_status,
                                'Key Created': key_create_date.strftime('%Y-%m-%d'),
                                'Key Last Used': last_used,
                                'Days Since Key Used': days_since_used,
                                'Last Used Service': last_used_service,
                                'Last Used Region': last_used_region
                            }
                            users_data.append(user_data)
                    else:
                        # User has no access keys
                        user_data = {
                            'Account ID': account_id,
                            'Account Name': account_name,
                            'User Name': username,
                            'User ARN': user_arn,
                            'User ID': user_id,
                            'User Created': create_date.strftime('%Y-%m-%d'),
                            'User Age (Days)': user_age_days,
                            'Password Last Used': password_last_used,
                            'MFA Enabled': mfa_enabled,
                            'MFA Devices': mfa_count,
                            'Access Key ID': 'No Keys',
                            'Key Status': 'N/A',
                            'Key Age (Days)': 0,
                            'Key Rotation Status': 'N/A',
                            'Key Created': 'N/A',
                            'Key Last Used': 'N/A',
                            'Days Since Key Used': 'N/A',
                            'Last Used Service': 'N/A',
                            'Last Used Region': 'N/A'
                        }
                        users_data.append(user_data)
                        
                except ClientError:
                    pass
                    
    except ClientError:
        pass
    except Exception:
        pass
    
    return users_data

def fetch_iam_users_data(selected_account_ids, all_accounts, role_name, age_threshold):
    """Fetch IAM users data for all selected accounts"""
    all_users = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_accounts = len(selected_account_ids)
    
    with ThreadPoolExecutor(max_workers=min(AWSConfig.MAX_WORKERS, total_accounts)) as executor:
        futures = {}
        
        for idx, account_id in enumerate(selected_account_ids):
            account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
            
            future = executor.submit(
                get_iam_users_for_account,
                account_id,
                account_name,
                role_name,
                age_threshold
            )
            futures[future] = (account_id, account_name, idx)
        
        for future in as_completed(futures):
            account_id, account_name, idx = futures[future]
            status_text.text(f"📡 Scanning IAM Users: {account_name} ({idx + 1}/{total_accounts})")
            
            try:
                users = future.result()
                all_users.extend(users)
            except Exception:
                pass
            
            progress_bar.progress((idx + 1) / total_accounts)
    
    progress_bar.empty()
    status_text.empty()
    
    return all_users

# ============================================================================
# BUTTON HANDLERS
# ============================================================================

# Check if fetch button was clicked
if st.session_state.get('iam_users_fetch_clicked', False):
    if not selected_account_ids:
        st.warning("⚠️ Please select at least one account.")
        st.session_state.iam_users_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning IAM users in {len(selected_account_ids)} account(s)..."):
            users_data = fetch_iam_users_data(
                selected_account_ids,
                all_accounts,
                AWSConfig.READONLY_ROLE_NAME,
                age_threshold
            )
            st.session_state.iam_users_data = users_data
            st.session_state.iam_users_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed_time = time.time() - start_time
        st.success(f"✅ Successfully fetched {len(users_data)} user records in {elapsed_time:.2f} seconds")
        st.session_state.iam_users_fetch_clicked = False

# ============================================================================
# DISPLAY RESULTS
# ============================================================================

if st.session_state.iam_users_data is not None:
    df = pd.DataFrame(st.session_state.iam_users_data)
    
    # Refresh button on main page
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        if st.session_state.iam_users_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.iam_users_last_refresh}")
    with col_refresh:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            if not selected_account_ids:
                st.warning("⚠️ Please select at least one account.")
            else:
                start_time = time.time()
                
                with st.spinner(f"🔍 Refreshing data..."):
                    users_data = fetch_iam_users_data(
                        selected_account_ids,
                        all_accounts,
                        AWSConfig.READONLY_ROLE_NAME,
                        age_threshold
                    )
                    st.session_state.iam_users_data = users_data
                    st.session_state.iam_users_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                elapsed_time = time.time() - start_time
                st.success(f"✅ Data refreshed ({len(users_data)} records in {elapsed_time:.2f} seconds)")
                st.rerun()
    
    if df.empty:
        st.info("ℹ️ No IAM users found in the selected accounts.")
    else:
        # Summary metrics
        st.subheader("📊 Summary Metrics")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        # Count unique users (some may have multiple keys)
        unique_users = df['User Name'].nunique()
        total_keys = len(df[df['Access Key ID'] != 'No Keys'])
        users_no_mfa = len(df[df['MFA Enabled'] == '❌ No']['User Name'].unique())
        overdue_keys = len(df[df['Key Rotation Status'] == '⚠️ Overdue'])
        active_keys = len(df[df['Key Status'] == 'Active'])
        
        with col1:
            st.metric("Total Users", unique_users)
        
        with col2:
            st.metric("🔑 Total Keys", total_keys)
        
        with col3:
            st.metric("⚠️ Overdue Keys", overdue_keys)
        
        with col4:
            st.metric("🔓 Active Keys", active_keys)
        
        with col5:
            st.metric("❌ No MFA", users_no_mfa)
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            account_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique().tolist()),
                default=sorted(df['Account Name'].unique().tolist())
            )
        
        with filter_col2:
            key_status_filter = st.multiselect(
                "Key Status:",
                options=sorted(df['Key Status'].unique().tolist()),
                default=sorted(df['Key Status'].unique().tolist())
            )
        
        with filter_col3:
            rotation_filter = st.multiselect(
                "Rotation Status:",
                options=sorted(df['Key Rotation Status'].unique().tolist()),
                default=sorted(df['Key Rotation Status'].unique().tolist())
            )
        
        # Apply filters
        filtered_df = df[
            (df['Account Name'].isin(account_filter)) &
            (df['Key Status'].isin(key_status_filter)) &
            (df['Key Rotation Status'].isin(rotation_filter))
        ]
        
        st.markdown("---")
        
        # Display data
        st.subheader(f"📋 IAM Users ({len(filtered_df)} records)")
        
        # Column selector
        available_columns = filtered_df.columns.tolist()
        default_columns = [
            'Account Name', 'User Name', 'User Age (Days)', 'MFA Enabled',
            'Access Key ID', 'Key Status', 'Key Age (Days)', 'Key Rotation Status',
            'Key Last Used', 'Last Used Service'
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
        
        # Download button
        st.markdown("---")
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download IAM Users Report (CSV)",
            data=csv,
            file_name=f"iam_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # Statistics
        with st.expander("📈 Additional Statistics"):
            stat_col1, stat_col2 = st.columns(2)
            
            with stat_col1:
                st.write("**Keys by Rotation Status:**")
                rotation_counts = filtered_df['Key Rotation Status'].value_counts()
                st.dataframe(rotation_counts, use_container_width=True)
                
                st.write("**MFA Status Distribution:**")
                mfa_counts = filtered_df.groupby('User Name')['MFA Enabled'].first().value_counts()
                st.dataframe(mfa_counts, use_container_width=True)
            
            with stat_col2:
                st.write("**Keys by Status:**")
                status_counts = filtered_df['Key Status'].value_counts()
                st.dataframe(status_counts, use_container_width=True)
                
                st.write("**Average Key Age by Account:**")
                avg_key_age = filtered_df[filtered_df['Key Age (Days)'] > 0].groupby('Account Name')['Key Age (Days)'].mean().round(0)
                st.dataframe(avg_key_age, use_container_width=True)

else:
    st.info("👈 Configure options in the sidebar and click 'Fetch Data' to begin.")
    
    st.markdown("""
    ### 👥 About IAM Users Dashboard
    
    This dashboard provides comprehensive insights into your IAM users across all accounts.
    
    **Information Displayed:**
    - User details (name, ARN, creation date, age)
    - Access key information (ID, status, age, rotation status)
    - Key usage tracking (last used date, service, region)
    - MFA status and device count
    - Password last used timestamp
    
    **Security Best Practices:**
    - Enable MFA for all users
    - Rotate access keys every 90 days
    - Remove unused keys
    - Monitor key usage regularly
    - Use IAM roles instead of keys where possible
    """)
```
