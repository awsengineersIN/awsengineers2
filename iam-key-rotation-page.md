# IAM Key Rotation Dashboard Page

Save this as: `pages/IAM_Key_Rotation.py`

```python
"""
IAM Access Key Rotation Dashboard Page

Displays IAM access keys and their age/rotation status across accounts.

Run: streamlit run main.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from modules.config import AWSConfig
from modules.iam import (
    AWSOrganizations, 
    AWSSession
)
from botocore.exceptions import ClientError

st.set_page_config(page_title="IAM Key Rotation", page_icon="🔑", layout="wide")

# Initialize session state
if 'iam_keys_data' not in st.session_state:
    st.session_state.iam_keys_data = None
if 'iam_keys_last_refresh' not in st.session_state:
    st.session_state.iam_keys_last_refresh = None

st.title("🔑 IAM Access Key Rotation Dashboard")

# Sidebar Configuration
st.sidebar.header("⚙️ Configuration")

all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Account selection
st.sidebar.subheader("📋 Account Selection")
account_options = {f"{acc['Name']} ({acc['Id']})": acc['Id'] for acc in all_accounts}

select_all = st.sidebar.checkbox("Select All Accounts", value=False, key="iam_select_all")

if select_all:
    selected_account_names = list(account_options.keys())
else:
    default_account = st.session_state.get('selected_account', {}).get('full_name')
    default_idx = 0
    if default_account and default_account in account_options:
        default_idx = list(account_options.keys()).index(default_account)
    
    selected_account_names = st.sidebar.multiselect(
        "Choose Accounts:",
        options=list(account_options.keys()),
        default=[list(account_options.keys())[default_idx]],
        help="Select one or more accounts",
        key="iam_accounts"
    )

selected_account_ids = [account_options[name] for name in selected_account_names]

# Age threshold
st.sidebar.subheader("⏰ Age Threshold")
age_threshold = st.sidebar.number_input(
    "Alert if key age exceeds (days):",
    min_value=1,
    max_value=365,
    value=90,
    help="Keys older than this will be highlighted",
    key="iam_threshold"
)

# Helper functions
def get_iam_keys_for_account(account_id, account_name, role_name, age_threshold):
    keys_data = []
    try:
        iam_client = AWSSession.get_client_for_account(
            'iam', account_id, role_name, 'us-east-1'  # IAM is global
        )
        
        # List all users
        paginator = iam_client.get_paginator('list_users')
        
        for page in paginator.paginate():
            for user in page['Users']:
                username = user['UserName']
                
                # Get access keys for this user
                try:
                    keys_response = iam_client.list_access_keys(UserName=username)
                    
                    for key in keys_response['AccessKeyMetadata']:
                        access_key_id = key['AccessKeyId']
                        create_date = key['CreateDate']
                        status = key['Status']
                        
                        # Calculate age
                        age_days = (datetime.now(create_date.tzinfo) - create_date).days
                        
                        # Determine rotation status
                        if age_days > age_threshold:
                            rotation_status = "⚠️ Overdue"
                        elif age_days > (age_threshold * 0.8):
                            rotation_status = "⚡ Soon"
                        else:
                            rotation_status = "✅ OK"
                        
                        # Get last used info
                        last_used = "Never"
                        last_used_service = "N/A"
                        try:
                            last_used_response = iam_client.get_access_key_last_used(
                                AccessKeyId=access_key_id
                            )
                            if 'LastUsedDate' in last_used_response.get('AccessKeyLastUsed', {}):
                                last_used_date = last_used_response['AccessKeyLastUsed']['LastUsedDate']
                                last_used = last_used_date.strftime('%Y-%m-%d %H:%M:%S')
                                last_used_service = last_used_response['AccessKeyLastUsed'].get('ServiceName', 'N/A')
                        except:
                            pass
                        
                        key_data = {
                            'Account ID': account_id,
                            'Account Name': account_name,
                            'User Name': username,
                            'Access Key ID': access_key_id,
                            'Status': status,
                            'Age (Days)': age_days,
                            'Rotation Status': rotation_status,
                            'Create Date': create_date.strftime('%Y-%m-%d'),
                            'Last Used': last_used,
                            'Last Used Service': last_used_service,
                            'User Created': user['CreateDate'].strftime('%Y-%m-%d')
                        }
                        keys_data.append(key_data)
                        
                except ClientError as e:
                    pass
                    
    except ClientError as e:
        pass
    except Exception as e:
        pass
    
    return keys_data

def fetch_iam_keys_data(selected_account_ids, all_accounts, role_name, age_threshold):
    all_keys = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_accounts = len(selected_account_ids)
    
    # IAM is global, but we can parallelize account scanning
    with ThreadPoolExecutor(max_workers=min(AWSConfig.MAX_WORKERS, total_accounts)) as executor:
        futures = {}
        
        for idx, account_id in enumerate(selected_account_ids):
            account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
            
            future = executor.submit(
                get_iam_keys_for_account,
                account_id,
                account_name,
                role_name,
                age_threshold
            )
            futures[future] = (account_id, account_name, idx)
        
        for future in as_completed(futures):
            account_id, account_name, idx = futures[future]
            status_text.text(f"📡 Scanning IAM Keys: {account_name} ({idx + 1}/{total_accounts})")
            
            try:
                keys = future.result()
                all_keys.extend(keys)
            except Exception as e:
                pass
            
            progress_bar.progress((idx + 1) / total_accounts)
    
    progress_bar.empty()
    status_text.empty()
    
    return all_keys

# Fetch/Refresh button
st.sidebar.markdown("---")
col1, col2 = st.sidebar.columns(2)

with col1:
    fetch_button = st.button("🔄 Fetch Access Keys", type="primary", use_container_width=True, key="iam_fetch")

with col2:
    refresh_button = st.button("🔁 Refresh Data", use_container_width=True, key="iam_refresh")

if fetch_button or refresh_button:
    if not selected_account_ids:
        st.warning("⚠️ Please select at least one account.")
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning IAM access keys in {len(selected_account_ids)} account(s)..."):
            keys_data = fetch_iam_keys_data(
                selected_account_ids,
                all_accounts,
                AWSConfig.READONLY_ROLE_NAME,
                age_threshold
            )
            st.session_state.iam_keys_data = keys_data
            st.session_state.iam_keys_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed_time = time.time() - start_time
        st.success(f"✅ Successfully fetched {len(keys_data)} access keys in {elapsed_time:.2f} seconds")

# Clear button
if st.sidebar.button("🗑️ Clear Data", use_container_width=True, key="iam_clear"):
    st.session_state.iam_keys_data = None
    st.session_state.iam_keys_last_refresh = None
    st.rerun()

# Display results
if st.session_state.iam_keys_last_refresh:
    st.caption(f"Last refreshed: {st.session_state.iam_keys_last_refresh}")

if st.session_state.iam_keys_data is not None:
    df = pd.DataFrame(st.session_state.iam_keys_data)
    
    if df.empty:
        st.info("ℹ️ No IAM access keys found in the selected accounts.")
    else:
        st.subheader("📊 Summary Metrics")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Keys", len(df))
        
        with col2:
            overdue_count = len(df[df['Rotation Status'] == '⚠️ Overdue'])
            st.metric("⚠️ Overdue", overdue_count)
        
        with col3:
            soon_count = len(df[df['Rotation Status'] == '⚡ Soon'])
            st.metric("⚡ Soon", soon_count)
        
        with col4:
            ok_count = len(df[df['Rotation Status'] == '✅ OK'])
            st.metric("✅ OK", ok_count)
        
        with col5:
            active_keys = len(df[df['Status'] == 'Active'])
            st.metric("🔓 Active", active_keys)
        
        st.markdown("---")
        st.subheader("🔍 Filters")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            account_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique().tolist()),
                default=sorted(df['Account Name'].unique().tolist()),
                key="iam_filter_account"
            )
        
        with filter_col2:
            status_filter = st.multiselect(
                "Key Status:",
                options=sorted(df['Status'].unique().tolist()),
                default=sorted(df['Status'].unique().tolist()),
                key="iam_filter_status"
            )
        
        with filter_col3:
            rotation_filter = st.multiselect(
                "Rotation Status:",
                options=sorted(df['Rotation Status'].unique().tolist()),
                default=sorted(df['Rotation Status'].unique().tolist()),
                key="iam_filter_rotation"
            )
        
        filtered_df = df[
            (df['Account Name'].isin(account_filter)) &
            (df['Status'].isin(status_filter)) &
            (df['Rotation Status'].isin(rotation_filter))
        ]
        
        st.markdown("---")
        st.subheader(f"📋 IAM Access Keys ({len(filtered_df)} keys)")
        
        available_columns = filtered_df.columns.tolist()
        default_columns = [
            'Account Name', 'User Name', 'Access Key ID', 'Status',
            'Age (Days)', 'Rotation Status', 'Last Used'
        ]
        
        selected_columns = st.multiselect(
            "Select columns to display:",
            options=available_columns,
            default=[col for col in default_columns if col in available_columns],
            key="iam_columns"
        )
        
        if selected_columns:
            display_df = filtered_df[selected_columns]
        else:
            display_df = filtered_df
        
        st.dataframe(display_df, use_container_width=True, height=500, hide_index=True)
        
        st.markdown("---")
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Access Keys Report (CSV)",
            data=csv,
            file_name=f"iam_access_keys_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=False
        )
        
        with st.expander("📈 Additional Statistics"):
            stat_col1, stat_col2 = st.columns(2)
            
            with stat_col1:
                st.write("**Keys by Rotation Status:**")
                rotation_counts = filtered_df['Rotation Status'].value_counts()
                st.dataframe(rotation_counts, use_container_width=True)
                
                st.write("**Average Key Age by Account:**")
                avg_age = filtered_df.groupby('Account Name')['Age (Days)'].mean().round(0)
                st.dataframe(avg_age, use_container_width=True)
            
            with stat_col2:
                st.write("**Keys by Status:**")
                status_counts = filtered_df['Status'].value_counts()
                st.dataframe(status_counts, use_container_width=True)
                
                st.write("**Users with Most Keys:**")
                user_counts = filtered_df['User Name'].value_counts().head(10)
                st.dataframe(user_counts, use_container_width=True)

else:
    st.info("👈 Configure options in the sidebar and click 'Fetch Access Keys' to begin.")
    
    st.markdown("""
    ### 🔑 About IAM Access Key Rotation
    
    Regular rotation of IAM access keys is a security best practice to reduce the risk of compromised credentials.
    
    **This dashboard helps you:**
    - Identify access keys that need rotation
    - Track key age and usage patterns
    - Ensure compliance with security policies
    - Monitor inactive keys
    
    **Best Practices:**
    - Rotate keys every 90 days
    - Delete unused keys
    - Use IAM roles instead of access keys where possible
    - Monitor key usage regularly
    """)
```
