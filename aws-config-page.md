# AWS Config Dashboard Page

Save this as: `pages/AWS_Config.py`

```python
"""
AWS Config Dashboard Page

Displays Config rules compliance status and configuration items across accounts.

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

st.set_page_config(page_title="AWS Config", page_icon="⚙️", layout="wide")

# Initialize session state
if 'config_data' not in st.session_state:
    st.session_state.config_data = None
if 'config_last_refresh' not in st.session_state:
    st.session_state.config_last_refresh = None

st.title("⚙️ AWS Config Dashboard")

# Sidebar Configuration
st.sidebar.header("⚙️ Configuration")

all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Account selection
st.sidebar.subheader("📋 Account Selection")
account_options = {f"{acc['Name']} ({acc['Id']})": acc['Id'] for acc in all_accounts}

select_all = st.sidebar.checkbox("Select All Accounts", value=False, key="cfg_select_all")

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
        key="cfg_accounts"
    )

selected_account_ids = [account_options[name] for name in selected_account_names]

# Region selection
st.sidebar.subheader("🌍 Region Selection")
region_mode = st.sidebar.radio(
    "Region Mode:",
    ["Common Regions", "All Regions", "Custom Regions"],
    help="Choose region scanning mode",
    key="cfg_region_mode"
)

try:
    if region_mode == "Common Regions":
        selected_regions = AWSRegions.get_common_regions()
        st.sidebar.info(f"Scanning {len(selected_regions)} common regions")
    elif region_mode == "All Regions":
        all_regions = AWSRegions.list_all_regions()
        selected_regions = all_regions
        st.sidebar.info(f"Scanning all {len(all_regions)} regions")
    else:
        all_regions = AWSRegions.list_all_regions()
        selected_regions = st.sidebar.multiselect(
            "Select Regions:",
            options=all_regions,
            default=['us-east-1'],
            key="cfg_regions"
        )
except Exception as e:
    st.sidebar.error(f"Error loading regions: {str(e)}")
    st.stop()

# Compliance filter
st.sidebar.subheader("✅ Compliance Filters")
compliance_filter = st.sidebar.multiselect(
    "Compliance Status:",
    options=["COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE", "INSUFFICIENT_DATA"],
    default=["NON_COMPLIANT"],
    key="cfg_compliance"
)

# Helper functions
def get_config_rules_in_region(region, account_id, account_name, role_name, compliance_filter):
    rules_data = []
    try:
        config_client = AWSSession.get_client_for_account(
            'config', account_id, role_name, region
        )
        
        # Get config rules
        response = config_client.describe_config_rules()
        rules = response.get('ConfigRules', [])
        
        for rule in rules:
            rule_name = rule['ConfigRuleName']
            
            # Get compliance status for this rule
            try:
                compliance_response = config_client.describe_compliance_by_config_rule(
                    ConfigRuleNames=[rule_name]
                )
                
                for compliance in compliance_response.get('ComplianceByConfigRules', []):
                    status = compliance.get('Compliance', {}).get('ComplianceType', 'N/A')
                    
                    if not compliance_filter or status in compliance_filter:
                        rule_data = {
                            'Account ID': account_id,
                            'Account Name': account_name,
                            'Region': region,
                            'Rule Name': rule_name,
                            'Rule ARN': rule.get('ConfigRuleArn', 'N/A'),
                            'Compliance Status': status,
                            'Description': rule.get('Description', 'N/A'),
                            'Source': rule.get('Source', {}).get('Owner', 'N/A'),
                            'Source Identifier': rule.get('Source', {}).get('SourceIdentifier', 'N/A'),
                            'Rule State': rule.get('ConfigRuleState', 'N/A')
                        }
                        rules_data.append(rule_data)
            except ClientError as e:
                pass
                
    except ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchConfigurationRecorderException':
            pass
    except Exception as e:
        pass
    
    return rules_data

def fetch_config_data(selected_account_ids, all_accounts, role_name, regions, compliance_filter):
    all_rules = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_accounts = len(selected_account_ids)
    
    for idx, account_id in enumerate(selected_account_ids):
        account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
        
        status_text.text(f"📡 Scanning AWS Config: {account_name} ({idx + 1}/{total_accounts})")
        
        with ThreadPoolExecutor(max_workers=AWSConfig.MAX_WORKERS) as executor:
            futures = {
                executor.submit(
                    get_config_rules_in_region,
                    region,
                    account_id,
                    account_name,
                    role_name,
                    compliance_filter
                ): region
                for region in regions
            }
            
            for future in as_completed(futures):
                try:
                    rules = future.result()
                    all_rules.extend(rules)
                except Exception as e:
                    pass
        
        progress_bar.progress((idx + 1) / total_accounts)
    
    progress_bar.empty()
    status_text.empty()
    
    return all_rules

# Fetch/Refresh button
st.sidebar.markdown("---")
col1, col2 = st.sidebar.columns(2)

with col1:
    fetch_button = st.button("🔄 Fetch Config Rules", type="primary", use_container_width=True, key="cfg_fetch")

with col2:
    refresh_button = st.button("🔁 Refresh Data", use_container_width=True, key="cfg_refresh")

if fetch_button or refresh_button:
    if not selected_account_ids:
        st.warning("⚠️ Please select at least one account.")
    elif not selected_regions:
        st.warning("⚠️ Please select at least one region.")
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning AWS Config in {len(selected_account_ids)} account(s) across {len(selected_regions)} region(s)..."):
            config_data = fetch_config_data(
                selected_account_ids,
                all_accounts,
                AWSConfig.READONLY_ROLE_NAME,
                selected_regions,
                compliance_filter
            )
            st.session_state.config_data = config_data
            st.session_state.config_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed_time = time.time() - start_time
        st.success(f"✅ Successfully fetched {len(config_data)} config rules in {elapsed_time:.2f} seconds")

# Clear button
if st.sidebar.button("🗑️ Clear Data", use_container_width=True, key="cfg_clear"):
    st.session_state.config_data = None
    st.session_state.config_last_refresh = None
    st.rerun()

# Display results
if st.session_state.config_last_refresh:
    st.caption(f"Last refreshed: {st.session_state.config_last_refresh}")

if st.session_state.config_data is not None:
    df = pd.DataFrame(st.session_state.config_data)
    
    if df.empty:
        st.info("ℹ️ No AWS Config rules found in the selected accounts and regions.")
        st.info("💡 Tip: AWS Config must be enabled in the regions you're scanning.")
    else:
        st.subheader("📊 Summary Metrics")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Rules", len(df))
        
        with col2:
            compliant_count = len(df[df['Compliance Status'] == 'COMPLIANT'])
            st.metric("✅ Compliant", compliant_count)
        
        with col3:
            non_compliant_count = len(df[df['Compliance Status'] == 'NON_COMPLIANT'])
            st.metric("❌ Non-Compliant", non_compliant_count)
        
        with col4:
            not_applicable = len(df[df['Compliance Status'] == 'NOT_APPLICABLE'])
            st.metric("⚪ Not Applicable", not_applicable)
        
        with col5:
            unique_accounts = df['Account ID'].nunique()
            st.metric("Accounts", unique_accounts)
        
        st.markdown("---")
        st.subheader("🔍 Filters")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            account_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique().tolist()),
                default=sorted(df['Account Name'].unique().tolist()),
                key="cfg_filter_account"
            )
        
        with filter_col2:
            region_filter = st.multiselect(
                "Region:",
                options=sorted(df['Region'].unique().tolist()),
                default=sorted(df['Region'].unique().tolist()),
                key="cfg_filter_region"
            )
        
        with filter_col3:
            source_filter = st.multiselect(
                "Rule Source:",
                options=sorted(df['Source'].unique().tolist()),
                default=sorted(df['Source'].unique().tolist()),
                key="cfg_filter_source"
            )
        
        filtered_df = df[
            (df['Account Name'].isin(account_filter)) &
            (df['Region'].isin(region_filter)) &
            (df['Source'].isin(source_filter))
        ]
        
        st.markdown("---")
        st.subheader(f"📋 AWS Config Rules ({len(filtered_df)} rules)")
        
        available_columns = filtered_df.columns.tolist()
        default_columns = [
            'Account Name', 'Region', 'Rule Name', 'Compliance Status',
            'Source', 'Rule State'
        ]
        
        selected_columns = st.multiselect(
            "Select columns to display:",
            options=available_columns,
            default=[col for col in default_columns if col in available_columns],
            key="cfg_columns"
        )
        
        if selected_columns:
            display_df = filtered_df[selected_columns]
        else:
            display_df = filtered_df
        
        st.dataframe(display_df, use_container_width=True, height=500, hide_index=True)
        
        st.markdown("---")
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Config Rules (CSV)",
            data=csv,
            file_name=f"config_rules_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=False
        )
        
        with st.expander("📈 Additional Statistics"):
            stat_col1, stat_col2 = st.columns(2)
            
            with stat_col1:
                st.write("**Rules by Compliance Status:**")
                compliance_counts = filtered_df['Compliance Status'].value_counts()
                st.dataframe(compliance_counts, use_container_width=True)
            
            with stat_col2:
                st.write("**Rules by Source:**")
                source_counts = filtered_df['Source'].value_counts()
                st.dataframe(source_counts, use_container_width=True)

else:
    st.info("👈 Configure options in the sidebar and click 'Fetch Config Rules' to begin.")
```
