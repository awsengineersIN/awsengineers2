# Security Hub Dashboard Page

Save this as: `pages/Security_Hub.py`

```python
"""
Security Hub Dashboard Page

Displays Security Hub findings and compliance status across accounts.

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
    AWSRegions, 
    AWSSession
)
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(page_title="Security Hub", page_icon="🔒", layout="wide")

# Initialize session state
if 'security_hub_data' not in st.session_state:
    st.session_state.security_hub_data = None
if 'security_hub_last_refresh' not in st.session_state:
    st.session_state.security_hub_last_refresh = None

# Header
st.title("🔒 Security Hub Dashboard")

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

select_all = st.sidebar.checkbox("Select All Accounts", value=False, key="sh_select_all")

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
        key="sh_accounts"
    )

selected_account_ids = [account_options[name] for name in selected_account_names]

# Region selection
st.sidebar.subheader("🌍 Region Selection")
region_mode = st.sidebar.radio(
    "Region Mode:",
    ["Common Regions", "All Regions", "Custom Regions"],
    help="Choose region scanning mode",
    key="sh_region_mode"
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
            key="sh_regions"
        )
except Exception as e:
    st.sidebar.error(f"Error loading regions: {str(e)}")
    st.stop()

# Severity filter
st.sidebar.subheader("⚠️ Finding Filters")
severity_filter = st.sidebar.multiselect(
    "Severity:",
    options=["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"],
    default=["CRITICAL", "HIGH"],
    key="sh_severity"
)

# Helper functions
def get_security_hub_findings_in_region(region, account_id, account_name, role_name, severity_filter):
    findings = []
    try:
        sh_client = AWSSession.get_client_for_account(
            'securityhub', account_id, role_name, region
        )
        
        try:
            sh_client.describe_hub()
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidAccessException':
                return []
            raise
        
        filters = {
            'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
            'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}]
        }
        
        if severity_filter:
            filters['SeverityLabel'] = [
                {'Value': sev, 'Comparison': 'EQUALS'} 
                for sev in severity_filter
            ]
        
        paginator = sh_client.get_paginator('get_findings')
        
        for page in paginator.paginate(Filters=filters, MaxResults=100):
            for finding in page['Findings']:
                finding_data = {
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'Finding ID': finding.get('Id', 'N/A'),
                    'Title': finding.get('Title', 'N/A'),
                    'Description': finding.get('Description', 'N/A')[:200] + '...',
                    'Severity': finding.get('Severity', {}).get('Label', 'N/A'),
                    'Resource Type': finding.get('Resources', [{}])[0].get('Type', 'N/A') if finding.get('Resources') else 'N/A',
                    'Resource ID': finding.get('Resources', [{}])[0].get('Id', 'N/A') if finding.get('Resources') else 'N/A',
                    'Compliance Status': finding.get('Compliance', {}).get('Status', 'N/A'),
                    'Workflow Status': finding.get('Workflow', {}).get('Status', 'N/A'),
                    'First Observed': finding.get('FirstObservedAt', 'N/A'),
                    'Last Observed': finding.get('LastObservedAt', 'N/A'),
                    'Generator ID': finding.get('GeneratorId', 'N/A')
                }
                findings.append(finding_data)
    except ClientError as e:
        pass
    except Exception as e:
        pass
    
    return findings

def fetch_security_hub_data(selected_account_ids, all_accounts, role_name, regions, severity_filter):
    all_findings = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_accounts = len(selected_account_ids)
    
    for idx, account_id in enumerate(selected_account_ids):
        account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
        
        status_text.text(f"📡 Scanning Security Hub: {account_name} ({idx + 1}/{total_accounts})")
        
        with ThreadPoolExecutor(max_workers=AWSConfig.MAX_WORKERS) as executor:
            futures = {
                executor.submit(
                    get_security_hub_findings_in_region,
                    region,
                    account_id,
                    account_name,
                    role_name,
                    severity_filter
                ): region
                for region in regions
            }
            
            for future in as_completed(futures):
                try:
                    findings = future.result()
                    all_findings.extend(findings)
                except Exception as e:
                    pass
        
        progress_bar.progress((idx + 1) / total_accounts)
    
    progress_bar.empty()
    status_text.empty()
    
    return all_findings

# Fetch/Refresh button
st.sidebar.markdown("---")
col1, col2 = st.sidebar.columns(2)

with col1:
    fetch_button = st.button("🔄 Fetch Findings", type="primary", use_container_width=True, key="sh_fetch")

with col2:
    refresh_button = st.button("🔁 Refresh Data", use_container_width=True, key="sh_refresh")

if fetch_button or refresh_button:
    if not selected_account_ids:
        st.warning("⚠️ Please select at least one account.")
    elif not selected_regions:
        st.warning("⚠️ Please select at least one region.")
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning Security Hub in {len(selected_account_ids)} account(s) across {len(selected_regions)} region(s)..."):
            findings_data = fetch_security_hub_data(
                selected_account_ids,
                all_accounts,
                AWSConfig.READONLY_ROLE_NAME,
                selected_regions,
                severity_filter
            )
            st.session_state.security_hub_data = findings_data
            st.session_state.security_hub_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed_time = time.time() - start_time
        st.success(f"✅ Successfully fetched {len(findings_data)} findings in {elapsed_time:.2f} seconds")

# Clear button
if st.sidebar.button("🗑️ Clear Data", use_container_width=True, key="sh_clear"):
    st.session_state.security_hub_data = None
    st.session_state.security_hub_last_refresh = None
    st.rerun()

# Display results
if st.session_state.security_hub_last_refresh:
    st.caption(f"Last refreshed: {st.session_state.security_hub_last_refresh}")

if st.session_state.security_hub_data is not None:
    df = pd.DataFrame(st.session_state.security_hub_data)
    
    if df.empty:
        st.info("ℹ️ No Security Hub findings found in the selected accounts and regions.")
        st.info("💡 Tip: Security Hub must be enabled in the regions you're scanning.")
    else:
        st.subheader("📊 Summary Metrics")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Findings", len(df))
        
        with col2:
            critical_count = len(df[df['Severity'] == 'CRITICAL'])
            st.metric("🔴 Critical", critical_count)
        
        with col3:
            high_count = len(df[df['Severity'] == 'HIGH'])
            st.metric("🟠 High", high_count)
        
        with col4:
            medium_count = len(df[df['Severity'] == 'MEDIUM'])
            st.metric("🟡 Medium", medium_count)
        
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
                key="sh_filter_account"
            )
        
        with filter_col2:
            region_filter = st.multiselect(
                "Region:",
                options=sorted(df['Region'].unique().tolist()),
                default=sorted(df['Region'].unique().tolist()),
                key="sh_filter_region"
            )
        
        with filter_col3:
            resource_type_filter = st.multiselect(
                "Resource Type:",
                options=sorted(df['Resource Type'].unique().tolist()),
                default=sorted(df['Resource Type'].unique().tolist()),
                key="sh_filter_resource"
            )
        
        filtered_df = df[
            (df['Account Name'].isin(account_filter)) &
            (df['Region'].isin(region_filter)) &
            (df['Resource Type'].isin(resource_type_filter))
        ]
        
        st.markdown("---")
        st.subheader(f"📋 Security Hub Findings ({len(filtered_df)} findings)")
        
        available_columns = filtered_df.columns.tolist()
        default_columns = [
            'Account Name', 'Region', 'Severity', 'Title',
            'Resource Type', 'Resource ID', 'Compliance Status'
        ]
        
        selected_columns = st.multiselect(
            "Select columns to display:",
            options=available_columns,
            default=[col for col in default_columns if col in available_columns],
            key="sh_columns"
        )
        
        if selected_columns:
            display_df = filtered_df[selected_columns]
        else:
            display_df = filtered_df
        
        st.dataframe(display_df, use_container_width=True, height=500, hide_index=True)
        
        st.markdown("---")
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Findings (CSV)",
            data=csv,
            file_name=f"security_hub_findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=False
        )
        
        with st.expander("📈 Additional Statistics"):
            stat_col1, stat_col2 = st.columns(2)
            
            with stat_col1:
                st.write("**Findings by Severity:**")
                severity_counts = filtered_df['Severity'].value_counts()
                st.dataframe(severity_counts, use_container_width=True)
            
            with stat_col2:
                st.write("**Findings by Resource Type:**")
                resource_counts = filtered_df['Resource Type'].value_counts().head(10)
                st.dataframe(resource_counts, use_container_width=True)

else:
    st.info("👈 Configure options in the sidebar and click 'Fetch Findings' to begin.")
```
