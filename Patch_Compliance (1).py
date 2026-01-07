"""
SSM Patch Compliance Dashboard

Features:
- Filter by account and region
- View patch compliance status across instances
- Patch compliance summary with aggregated statistics
- Detailed patch compliance report by instance
- Patch details with severity breakdown
- Tabs: Patch Groups, Instances, Available Patches, Severity Summary
- Color-coded compliance status (RED for Non-Compliant, YELLOW for Unspecified, GREEN for Compliant)
- Metrics: Compliant, Non-Compliant, Unspecified instances
- CSV export
- Graphs and charts for analysis

Uses your utils.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import boto3
import plotly.express as px

from utils import (
    assume_role,
    setup_account_filter,
    get_account_name_by_id,
)
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(page_title="Patch Compliance", page_icon="🔧", layout="wide")

# Initialize session state
if 'patch_data' not in st.session_state:
    st.session_state.patch_data = {
        'summary': None,
        'instances': None,
        'patches': None
    }
if 'patch_last_refresh' not in st.session_state:
    st.session_state.patch_last_refresh = None
if 'patch_errors' not in st.session_state:
    st.session_state.patch_errors = []

st.title("🔧 SSM Patch Compliance Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="patch")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_ssm_client(account_id, role_name, region):
    """Get SSM client"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'ssm',
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_ec2_client(account_id, role_name, region):
    """Get EC2 client"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'ec2',
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_patch_compliance(account_id, account_name, region, role_name):
    """Get patch compliance data for an account/region"""
    summary_data = []
    instance_data = []
    patch_data = []
    errors = []
    
    try:
        ssm = get_ssm_client(account_id, role_name, region)
        ec2 = get_ec2_client(account_id, role_name, region)
        
        if not ssm or not ec2:
            errors.append(f"❌ {account_name}/{region}: Failed to get SSM/EC2 client")
            return summary_data, instance_data, patch_data, errors
        
        # ==================== COMPLIANCE SUMMARY ====================
        try:
            paginator = ssm.get_paginator('describe_patch_groups')
            page_iterator = paginator.paginate()
            
            for page in page_iterator:
                for patch_group in page.get('Mappings', []):
                    group_name = patch_group.get('PatchGroup', 'N/A')
                    baseline_id = patch_group.get('BaselineIdentity', {}).get('BaselineId', 'N/A')
                    
                    # Get compliance summary for this patch group
                    try:
                        compliance_resp = ssm.describe_patch_group_state(PatchGroup=group_name)
                        
                        instances_count = compliance_resp.get('Instances', 0)
                        compliant = compliance_resp.get('InstancesWithInstalledPatches', 0)
                        non_compliant = compliance_resp.get('InstancesWithFailedPatches', 0)
                        unspecified = compliance_resp.get('InstancesWithUnreportedNotApplicablePatches', 0)
                        
                        # Only include patch groups with at least one instance
                        if instances_count > 0:
                            summary_data.append({
                                'Account Name': account_name,
                                'Account ID': account_id,
                                'Region': region,
                                'Patch Group': group_name,
                                'Baseline ID': baseline_id,
                                'Instances Count': instances_count,
                                'Compliant': compliant,
                                'Non-Compliant': non_compliant,
                                'Unspecified': unspecified
                            })
                    except Exception as e:
                        pass
        
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching patch groups - {str(e)}")
        
        # ==================== INSTANCE COMPLIANCE ====================
        try:
            # Get instance patch states for all instances
            paginator = ssm.get_paginator('describe_instance_patch_states')
            page_iterator = paginator.paginate()
            
            for page in page_iterator:
                for patch_state in page.get('InstancePatchStates', []):
                    instance_id = patch_state.get('InstanceId', '')
                    
                    # Determine compliance status based on patch counts
                    installed = patch_state.get('InstalledCount', 0)
                    missing = patch_state.get('MissingCount', 0)
                    failed = patch_state.get('FailedCount', 0)
                    
                    if failed > 0 or missing > 0:
                        compliance_status = 'NON_COMPLIANT'
                    else:
                        compliance_status = 'COMPLIANT'
                    
                    # Get instance details from EC2
                    try:
                        ec2_resp = ec2.describe_instances(InstanceIds=[instance_id])
                        
                        if ec2_resp['Reservations']:
                            instance = ec2_resp['Reservations'][0]['Instances'][0]
                            instance_name = next(
                                (tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'),
                                instance_id
                            )
                            platform = instance.get('Platform', 'windows') or 'linux'
                            state = instance['State']['Name']
                            launch_time = instance['LaunchTime'].strftime('%Y-%m-%d %H:%M:%S') if 'LaunchTime' in instance else 'N/A'
                            
                            instance_data.append({
                                'Account Name': account_name,
                                'Account ID': account_id,
                                'Region': region,
                                'Instance ID': instance_id,
                                'Instance Name': instance_name,
                                'Platform': platform,
                                'Compliance Status': compliance_status,
                                'Installed Patches': installed,
                                'Missing Patches': missing,
                                'Failed Patches': failed,
                                'Launch Time': launch_time,
                                'Instance State': state
                            })
                    except Exception as e:
                        # Instance might not exist anymore
                        pass
        
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching instance patch states - {str(e)}")
        
        # ==================== PATCH DETAILS ====================
        try:
            paginator = ssm.get_paginator('describe_available_patches')
            page_iterator = paginator.paginate()
            
            for page in page_iterator:
                for patch in page.get('Patches', []):
                    patch_data.append({
                        'Account Name': account_name,
                        'Account ID': account_id,
                        'Region': region,
                        'Patch ID': patch.get('Id', 'N/A'),
                        'Title': patch.get('Title', 'N/A'),
                        'Classification': patch.get('Classification', 'N/A'),
                        'Severity': patch.get('Severity', 'N/A'),
                        'Release Date': str(patch.get('ReleaseDate', 'N/A'))
                    })
        
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching patch details - {str(e)}")
    
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return summary_data, instance_data, patch_data, errors

def fetch_data(account_ids, all_accounts, regions, role_name):
    """Fetch patch compliance data with parallel processing"""
    all_summary = []
    all_instances = []
    all_patches = []
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(account_ids) * len(regions)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        
        for account_id in account_ids:
            account_name = get_account_name_by_id(account_id, all_accounts)
            for region in regions:
                future = executor.submit(get_patch_compliance, account_id, account_name, region, role_name)
                futures[future] = (account_id, account_name, region)
        
        for future in as_completed(futures):
            account_id, account_name, region = futures[future]
            completed += 1
            status_text.text(f"📡 {account_name}/{region} ({completed}/{total})")
            progress_bar.progress(completed / total)
            
            try:
                summary, instances, patches, errors = future.result()
                all_summary.extend(summary)
                all_instances.extend(instances)
                all_patches.extend(patches)
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"❌ {account_name}/{region}: Failed - {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return all_summary, all_instances, all_patches, all_errors

# ============================================================================
# FETCH BUTTON
# ============================================================================

if st.session_state.get('patch_fetch_clicked', False):
    if not account_ids or not regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.patch_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning patch compliance..."):
            summary, instances, patches, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
            st.session_state.patch_data = {
                'summary': summary,
                'instances': instances,
                'patches': patches
            }
            st.session_state.patch_errors = errors
            st.session_state.patch_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        total_items = len(summary) + len(instances) + len(patches)
        if total_items > 0:
            st.success(f"✅ Patch compliance data fetched in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No patch data found in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.patch_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.patch_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.patch_errors:
            st.write(error)

if st.session_state.patch_data['summary'] is not None:
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.patch_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.patch_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                summary, instances, patches, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
                st.session_state.patch_data = {
                    'summary': summary,
                    'instances': instances,
                    'patches': patches
                }
                st.session_state.patch_errors = errors
                st.session_state.patch_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed in {elapsed:.2f}s")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    st.markdown("---")
    
    summary_df = pd.DataFrame(st.session_state.patch_data['summary']) if st.session_state.patch_data['summary'] else pd.DataFrame()
    instance_df = pd.DataFrame(st.session_state.patch_data['instances']) if st.session_state.patch_data['instances'] else pd.DataFrame()
    patch_df = pd.DataFrame(st.session_state.patch_data['patches']) if st.session_state.patch_data['patches'] else pd.DataFrame()
    
    if summary_df.empty and instance_df.empty and patch_df.empty:
        st.info("ℹ️ No patch compliance data found.")
    else:
        # ==================== METRICS ====================
        st.subheader("📊 Summary")
        
        compliant_count = len(instance_df[instance_df['Compliance Status'] == 'COMPLIANT']) if not instance_df.empty else 0
        non_compliant_count = len(instance_df[instance_df['Compliance Status'] == 'NON_COMPLIANT']) if not instance_df.empty else 0
        total_instances = len(instance_df) if not instance_df.empty else 0
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("🟢 Compliant", compliant_count)
        with col2:
            st.metric("🔴 Non-Compliant", non_compliant_count)
        with col3:
            total_missing = int(instance_df['Missing Patches'].sum()) if not instance_df.empty else 0
            st.metric("📦 Missing Patches", total_missing)
        with col4:
            st.metric("Total Instances", total_instances)
        with col5:
            if total_instances > 0:
                compliance_pct = (compliant_count / total_instances) * 100
                st.metric("Compliance %", f"{compliance_pct:.1f}%")
        
        st.markdown("---")
        
        # ==================== FILTERS ====================
        st.subheader("🔍 Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if not instance_df.empty:
                accounts_filter = st.multiselect(
                    "Account:",
                    options=sorted(instance_df['Account Name'].unique()),
                    default=sorted(instance_df['Account Name'].unique()),
                    key="patch_account"
                )
            else:
                accounts_filter = []
        
        with col2:
            if not instance_df.empty:
                regions_filter = st.multiselect(
                    "Region:",
                    options=sorted(instance_df['Region'].unique()),
                    default=sorted(instance_df['Region'].unique()),
                    key="patch_region"
                )
            else:
                regions_filter = []
        
        with col3:
            if not instance_df.empty:
                status_filter = st.multiselect(
                    "Compliance Status:",
                    options=sorted(instance_df['Compliance Status'].unique()),
                    default=sorted(instance_df['Compliance Status'].unique()),
                    key="patch_status"
                )
            else:
                status_filter = []
        
        if not instance_df.empty:
            filtered = instance_df[
                (instance_df['Account Name'].isin(accounts_filter)) &
                (instance_df['Region'].isin(regions_filter)) &
                (instance_df['Compliance Status'].isin(status_filter))
            ]
        else:
            filtered = instance_df
        
        st.markdown("---")
        
        # ==================== OVERVIEW GRAPHS ====================
        if not filtered.empty:
            st.subheader("📈 Overview")
            
            graph_col1, graph_col2 = st.columns(2)
            
            # Compliance Status Distribution
            with graph_col1:
                status_counts = filtered['Compliance Status'].value_counts()
                colors = {'COMPLIANT': '#28a745', 'NON_COMPLIANT': '#dc3545'}
                fig_status = px.pie(
                    values=status_counts.values,
                    names=status_counts.index,
                    title="Compliance Status Distribution",
                    hole=0.3,
                    color_discrete_map=colors
                )
                st.plotly_chart(fig_status, use_container_width=True)
            
            # Compliance by Account
            with graph_col2:
                if not filtered.empty and 'Account Name' in filtered.columns:
                    account_counts = filtered['Account Name'].value_counts()
                    fig_account = px.bar(
                        x=account_counts.index,
                        y=account_counts.values,
                        title="Instances by Account",
                        labels={'x': 'Account', 'y': 'Count'}
                    )
                    fig_account.update_traces(marker_color='#ff7f0e')
                    st.plotly_chart(fig_account, use_container_width=True)
            
            graph_col3, graph_col4 = st.columns(2)
            
            # Instances by Platform
            with graph_col3:
                if not filtered.empty and 'Platform' in filtered.columns:
                    platform_counts = filtered['Platform'].value_counts()
                    fig_platform = px.bar(
                        x=platform_counts.index,
                        y=platform_counts.values,
                        title="Instances by Platform",
                        labels={'x': 'Platform', 'y': 'Count'}
                    )
                    fig_platform.update_traces(marker_color='#1f77b4')
                    st.plotly_chart(fig_platform, use_container_width=True)
            
            # Compliance by Region
            with graph_col4:
                if not filtered.empty and 'Region' in filtered.columns:
                    region_counts = filtered['Region'].value_counts()
                    fig_region = px.bar(
                        x=region_counts.index,
                        y=region_counts.values,
                        title="Instances by Region",
                        labels={'x': 'Region', 'y': 'Count'}
                    )
                    fig_region.update_traces(marker_color='#2ca02c')
                    st.plotly_chart(fig_region, use_container_width=True)
            
            st.markdown("---")
        
        # ==================== TABS ====================
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Patch Groups", "🖥️ Instances", "🔵 Available Patches", "📊 Severity Summary"])
        
        # TAB 1: PATCH GROUPS
        with tab1:
            st.subheader("Patch Compliance Summary by Patch Group")
            
            if not summary_df.empty:
                display_cols = ['Patch Group', 'Baseline ID', 'Instances Count', 'Compliant', 'Non-Compliant', 'Unspecified', 'Account Name', 'Region']
                display_df = summary_df[display_cols].reset_index(drop=True)
                
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    height=500,
                    hide_index=True
                )
                
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Patch Groups CSV",
                    data=csv,
                    file_name=f"patch_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("ℹ️ No patch group data available.")
        
        # TAB 2: INSTANCES
        with tab2:
            st.subheader("Instance Patch Compliance Report")
            
            if not filtered.empty:
                display_cols = ['Instance ID', 'Instance Name', 'Platform', 'Compliance Status', 'Installed Patches', 'Missing Patches', 'Failed Patches', 'Instance State', 'Launch Time', 'Account Name', 'Region']
                display_df = filtered[display_cols].sort_values('Compliance Status').reset_index(drop=True)
                
                def highlight_compliance(row):
                    status = row['Compliance Status']
                    if status == 'NON_COMPLIANT':
                        return ['background-color: #f8d7da'] * len(row)
                    else:
                        return ['background-color: #d4edda'] * len(row)
                
                st.dataframe(
                    display_df.style.apply(highlight_compliance, axis=1),
                    use_container_width=True,
                    height=500,
                    hide_index=True
                )
                
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Instances CSV",
                    data=csv,
                    file_name=f"patch_instances_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("ℹ️ No instance data available.")
        
        # TAB 3: AVAILABLE PATCHES
        with tab3:
            st.subheader("Available Patches")
            
            if not patch_df.empty:
                # Filter unique patches by ID
                unique_patches = patch_df.drop_duplicates(subset=['Patch ID']).copy()
                
                display_cols = ['Patch ID', 'Title', 'Classification', 'Severity', 'Release Date']
                display_df = unique_patches[display_cols].sort_values('Severity').reset_index(drop=True)
                
                def highlight_severity(row):
                    severity = row['Severity']
                    if severity == 'Critical':
                        return ['background-color: #dc3545'] * len(row)
                    elif severity == 'High':
                        return ['background-color: #fd7e14'] * len(row)
                    elif severity == 'Medium':
                        return ['background-color: #ffc107'] * len(row)
                    else:
                        return ['background-color: #d4edda'] * len(row)
                
                st.dataframe(
                    display_df.style.apply(highlight_severity, axis=1),
                    use_container_width=True,
                    height=500,
                    hide_index=True
                )
                
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Patches CSV",
                    data=csv,
                    file_name=f"available_patches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("ℹ️ No patch data available.")
        
        # TAB 4: SEVERITY SUMMARY
        with tab4:
            st.subheader("Patches by Severity")
            
            if not patch_df.empty:
                severity_counts = patch_df['Severity'].value_counts()
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    fig_severity = px.pie(
                        values=severity_counts.values,
                        names=severity_counts.index,
                        title="Patches by Severity",
                        hole=0.3
                    )
                    st.plotly_chart(fig_severity, use_container_width=True)
                
                with col2:
                    fig_classification = px.bar(
                        x=patch_df['Classification'].value_counts().index,
                        y=patch_df['Classification'].value_counts().values,
                        title="Patches by Classification",
                        labels={'x': 'Classification', 'y': 'Count'}
                    )
                    fig_classification.update_traces(marker_color='#1f77b4')
                    st.plotly_chart(fig_classification, use_container_width=True)
                
                with col3:
                    severity_by_class = patch_df.groupby(['Classification', 'Severity']).size().unstack(fill_value=0)
                    fig_heatmap = px.bar(
                        severity_by_class,
                        title="Severity by Classification",
                        barmode='group'
                    )
                    st.plotly_chart(fig_heatmap, use_container_width=True)
            else:
                st.info("ℹ️ No patch severity data available.")

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
