"""
AWS Config Dashboard

Uses your utils.py with proper data handling.
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
st.set_page_config(page_title="AWS Config", page_icon="⚙️", layout="wide")

# Initialize session state
if 'config_data' not in st.session_state:
    st.session_state.config_data = None
if 'config_last_refresh' not in st.session_state:
    st.session_state.config_last_refresh = None
if 'config_errors' not in st.session_state:
    st.session_state.config_errors = []

st.title("⚙️ AWS Config Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="config")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_config_client(account_id, role_name, region):
    """Get Config client using your assume_role function"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'config',
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_config_rules(region, account_id, account_name, role_name):
    """Get AWS Config rules compliance"""
    rules_data = []
    errors = []
    
    try:
        config_client = get_config_client(account_id, role_name, region)
        if not config_client:
            errors.append(f"❌ {account_name}/{region}: Failed to get Config client")
            return rules_data, errors
        
        # Get all config rules
        paginator = config_client.get_paginator('describe_config_rules')
        
        for page in paginator.paginate():
            for rule in page['ConfigRules']:
                rule_name = rule['ConfigRuleName']
                
                # Get compliance status
                try:
                    compliance = config_client.describe_compliance_by_config_rule(
                        ConfigRuleNames=[rule_name]
                    )
                    
                    if compliance['ComplianceByConfigRules']:
                        compliance_type = compliance['ComplianceByConfigRules'][0]['Compliance'].get('ComplianceType', 'INSUFFICIENT_DATA')
                    else:
                        compliance_type = 'INSUFFICIENT_DATA'
                        
                except:
                    compliance_type = 'INSUFFICIENT_DATA'
                
                # Get description
                description = rule.get('Description', 'No description')
                if description and len(description) > 200:
                    description = description[:200] + '...'
                
                rules_data.append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'Rule Name': rule_name,
                    'Compliance': compliance_type,
                    'Source': rule.get('Source', {}).get('Owner', 'Unknown'),
                    'Description': description
                })
                
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'NoSuchConfigurationRecorderException':
            errors.append(f"ℹ️ {account_name}/{region}: AWS Config not enabled")
        else:
            errors.append(f"⚠️ {account_name}/{region}: Cannot access Config - {str(e)}")
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return rules_data, errors

def fetch_data(account_ids, all_accounts, role_name, regions):
    """Fetch data with parallel processing"""
    all_data = []
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        
        for account_id in account_ids:
            account_name = get_account_name_by_id(account_id, all_accounts)
            for region in regions:
                future = executor.submit(get_config_rules, region, account_id, account_name, role_name)
                futures[future] = (account_id, account_name, region)
        
        total = len(futures)
        completed = 0
        
        for future in as_completed(futures):
            account_id, account_name, region = futures[future]
            completed += 1
            status_text.text(f"📡 {account_name} / {region} ({completed}/{total})")
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

if st.session_state.get('config_fetch_clicked', False):
    if not account_ids or not regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.config_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning AWS Config..."):
            data, errors = fetch_data(account_ids, all_accounts, "readonly-role", regions)
            st.session_state.config_data = data
            st.session_state.config_errors = errors
            st.session_state.config_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if data:
            st.success(f"✅ Found {len(data)} config rules in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No config rules in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.config_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.config_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.config_errors:
            st.write(error)

if st.session_state.config_data is not None:
    df = pd.DataFrame(st.session_state.config_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.config_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.config_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                data, errors = fetch_data(account_ids, all_accounts, "readonly-role", regions)
                st.session_state.config_data = data
                st.session_state.config_errors = errors
                st.session_state.config_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed ({len(data)} rules in {elapsed:.2f}s)")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df.empty:
        st.info("ℹ️ No AWS Config rules found.")
    else:
        # Metrics
        st.subheader("📊 Summary")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Rules", len(df))
        with col2:
            compliant = len(df[df['Compliance'] == 'COMPLIANT'])
            st.metric("✅ Compliant", compliant)
        with col3:
            non_compliant = len(df[df['Compliance'] == 'NON_COMPLIANT'])
            st.metric("❌ Non-Compliant", non_compliant)
        with col4:
            insufficient = len(df[df['Compliance'] == 'INSUFFICIENT_DATA'])
            st.metric("⚠️ Insufficient", insufficient)
        with col5:
            st.metric("Accounts", df['Account ID'].nunique())
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            compliance = st.multiselect(
                "Compliance:",
                options=sorted(df['Compliance'].unique()),
                default=sorted(df['Compliance'].unique())
            )
        
        with col2:
            regions_filter = st.multiselect(
                "Region:",
                options=sorted(df['Region'].unique()),
                default=sorted(df['Region'].unique())
            )
        
        with col3:
            accounts_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique()),
                default=sorted(df['Account Name'].unique())
            )
        
        filtered = df[
            (df['Compliance'].isin(compliance)) &
            (df['Region'].isin(regions_filter)) &
            (df['Account Name'].isin(accounts_filter))
        ]
        
        st.markdown("---")
        
        # Data table
        st.subheader(f"📋 Config Rules ({len(filtered)} items)")
        st.dataframe(filtered, use_container_width=True, height=500, hide_index=True)
        
        # Download
        st.markdown("---")
        csv = filtered.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"aws_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
