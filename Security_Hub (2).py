"""
Security Hub Dashboard - Fixed (No Empty Rows)

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
st.set_page_config(page_title="Security Hub", page_icon="🔒", layout="wide")

# Initialize session state
if 'securityhub_data' not in st.session_state:
    st.session_state.securityhub_data = None
if 'securityhub_last_refresh' not in st.session_state:
    st.session_state.securityhub_last_refresh = None
if 'securityhub_errors' not in st.session_state:
    st.session_state.securityhub_errors = []

st.title("🔒 Security Hub Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="securityhub")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_security_hub_client(account_id, role_name, region):
    """Get Security Hub client using your assume_role function"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'securityhub',
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_security_hub_findings(region, account_id, account_name, role_name):
    """Get Security Hub findings for a specific region"""
    findings = []
    errors = []
    
    try:
        sh_client = get_security_hub_client(account_id, role_name, region)
        if not sh_client:
            errors.append(f"❌ {account_name}/{region}: Failed to get client")
            return findings, errors
        
        # Check if Security Hub is enabled
        try:
            sh_client.describe_hub()
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'InvalidAccessException':
                errors.append(f"ℹ️ {account_name}/{region}: Security Hub not enabled")
            else:
                errors.append(f"⚠️ {account_name}/{region}: Cannot access Security Hub - {str(e)}")
            return findings, errors
        
        # Get active findings
        try:
            response = sh_client.get_findings(
                Filters={
                    'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                    'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}]
                },
                MaxResults=100
            )
            
            for finding in response.get('Findings', []):
                # Extract resource info safely
                resources = finding.get('Resources', [])
                resource_type = resources[0].get('Type', 'Unknown') if resources else 'Unknown'
                resource_id = resources[0].get('Id', 'Unknown') if resources else 'Unknown'
                
                # Format dates properly
                created_at = finding.get('CreatedAt', '')
                if created_at and hasattr(created_at, 'strftime'):
                    created_at = created_at.strftime('%Y-%m-%d %H:%M')
                elif not created_at:
                    created_at = 'Unknown'
                
                updated_at = finding.get('UpdatedAt', '')
                if updated_at and hasattr(updated_at, 'strftime'):
                    updated_at = updated_at.strftime('%Y-%m-%d %H:%M')
                elif not updated_at:
                    updated_at = 'Unknown'
                
                # Get generator ID
                generator_id = finding.get('GeneratorId', 'Unknown')
                if generator_id != 'Unknown' and '/' in generator_id:
                    generator_id = generator_id.split('/')[-1]
                
                # Get description
                description = finding.get('Description', 'No description')
                if description and len(description) > 200:
                    description = description[:200] + '...'
                
                finding_data = {
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'Title': finding.get('Title', 'No Title'),
                    'Severity': finding.get('Severity', {}).get('Label', 'INFORMATIONAL'),
                    'Status': finding.get('Compliance', {}).get('Status', 'UNKNOWN'),
                    'Resource Type': resource_type,
                    'Resource ID': resource_id,
                    'Generator ID': generator_id,
                    'Created At': created_at,
                    'Updated At': updated_at,
                    'Description': description,
                }
                findings.append(finding_data)
            
            if response.get('NextToken'):
                errors.append(f"ℹ️ {account_name}/{region}: Showing first 100 findings (more available)")
                
        except ClientError as e:
            errors.append(f"❌ {account_name}/{region}: Error fetching findings - {str(e)}")
            
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return findings, errors

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
                future = executor.submit(get_security_hub_findings, region, account_id, account_name, role_name)
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

if st.session_state.get('securityhub_fetch_clicked', False):
    if not account_ids or not regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.securityhub_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning Security Hub..."):
            data, errors = fetch_data(account_ids, all_accounts, "readonly-role", regions)
            st.session_state.securityhub_data = data
            st.session_state.securityhub_errors = errors
            st.session_state.securityhub_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if data:
            st.success(f"✅ Found {len(data)} findings in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No findings in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.securityhub_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.securityhub_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.securityhub_errors:
            st.write(error)

if st.session_state.securityhub_data is not None:
    df = pd.DataFrame(st.session_state.securityhub_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.securityhub_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.securityhub_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                data, errors = fetch_data(account_ids, all_accounts, "readonly-role", regions)
                st.session_state.securityhub_data = data
                st.session_state.securityhub_errors = errors
                st.session_state.securityhub_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed ({len(data)} findings in {elapsed:.2f}s)")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df.empty:
        st.info("ℹ️ No Security Hub findings found.")
    else:
        # Metrics
        st.subheader("📊 Summary")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Findings", len(df))
        with col2:
            critical = len(df[df['Severity'] == 'CRITICAL'])
            st.metric("🔴 Critical", critical)
        with col3:
            high = len(df[df['Severity'] == 'HIGH'])
            st.metric("🟠 High", high)
        with col4:
            medium = len(df[df['Severity'] == 'MEDIUM'])
            st.metric("🟡 Medium", medium)
        with col5:
            st.metric("Accounts", df['Account ID'].nunique())
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            severity = st.multiselect(
                "Severity:",
                options=sorted(df['Severity'].unique()),
                default=sorted(df['Severity'].unique())
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
            (df['Severity'].isin(severity)) &
            (df['Region'].isin(regions_filter)) &
            (df['Account Name'].isin(accounts_filter))
        ]
        
        st.markdown("---")
        
        # Data table
        st.subheader(f"📋 Findings ({len(filtered)} items)")
        st.dataframe(filtered, use_container_width=True, height=500, hide_index=True)
        
        # Download
        st.markdown("---")
        csv = filtered.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"securityhub_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
