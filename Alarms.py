"""
CloudWatch Alarms Dashboard

Features:
- Filter by account and region
- View open/alarming CloudWatch alarms
- Detailed information: alarm name, state, duration, description, metrics
- Tabs: All Alarms, Triggered Alarms, Recently Changed
- Metrics: Alarm count by state, alarm count by namespace, duration distribution
- Color-coded alarm states (RED for ALARM, YELLOW for INSUFFICIENT_DATA, GREEN for OK)
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
st.set_page_config(page_title="CloudWatch Alarms", page_icon="🚨", layout="wide")

# Initialize session state
if 'alarms_data' not in st.session_state:
    st.session_state.alarms_data = None
if 'alarms_last_refresh' not in st.session_state:
    st.session_state.alarms_last_refresh = None
if 'alarms_errors' not in st.session_state:
    st.session_state.alarms_errors = []

st.title("🚨 CloudWatch Alarms Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="alarms")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_cloudwatch_client(account_id, role_name, region):
    """Get CloudWatch client"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'cloudwatch',
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_alarms(account_id, account_name, region, role_name):
    """Get CloudWatch alarms for an account/region"""
    alarms = []
    errors = []
    
    try:
        cw = get_cloudwatch_client(account_id, role_name, region)
        if not cw:
            errors.append(f"❌ {account_name}/{region}: Failed to get CloudWatch client")
            return alarms, errors
        
        # Get all alarms (including ALARM, INSUFFICIENT_DATA, OK states)
        paginator = cw.get_paginator('describe_alarms')
        page_iterator = paginator.paginate()
        
        for page in page_iterator:
            for alarm in page.get('MetricAlarms', []):
                state_value = alarm.get('StateValue', 'UNKNOWN')
                state_updated = alarm.get('StateUpdatedTimestamp', datetime.now())
                
                # Calculate duration in alarm state
                if isinstance(state_updated, str):
                    try:
                        state_updated = datetime.fromisoformat(state_updated.replace('Z', '+00:00'))
                    except:
                        state_updated = datetime.now()
                
                duration = datetime.now(state_updated.tzinfo) - state_updated
                duration_hours = int(duration.total_seconds() / 3600)
                duration_days = duration_hours // 24
                duration_str = f"{duration_days}d {duration_hours % 24}h" if duration_days > 0 else f"{duration_hours}h"
                
                # Get metric details
                metric_name = alarm.get('MetricName', 'N/A')
                namespace = alarm.get('Namespace', 'N/A')
                statistic = alarm.get('Statistic', 'N/A')
                threshold = alarm.get('Threshold', 'N/A')
                comparison = alarm.get('ComparisonOperator', 'N/A')
                
                alarms.append({
                    'Account Name': account_name,
                    'Account ID': account_id,
                    'Region': region,
                    'Alarm Name': alarm['AlarmName'],
                    'Alarm ARN': alarm['AlarmArn'],
                    'State': state_value,
                    'State Updated': state_updated.strftime('%Y-%m-%d %H:%M:%S') if isinstance(state_updated, datetime) else str(state_updated),
                    'In Alarm Since': duration_str,
                    'Description': alarm.get('AlarmDescription', 'N/A'),
                    'Metric Name': metric_name,
                    'Namespace': namespace,
                    'Statistic': statistic,
                    'Threshold': threshold,
                    'Comparison': comparison,
                    'Period (s)': alarm.get('Period', 'N/A'),
                    'Evaluation Periods': alarm.get('EvaluationPeriods', 'N/A'),
                    'Actions Enabled': alarm.get('ActionsEnabled', False)
                })
    
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return alarms, errors

def fetch_data(account_ids, all_accounts, regions, role_name):
    """Fetch alarm data with parallel processing"""
    all_data = []
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
                future = executor.submit(get_alarms, account_id, account_name, region, role_name)
                futures[future] = (account_id, account_name, region)
        
        for future in as_completed(futures):
            account_id, account_name, region = futures[future]
            completed += 1
            status_text.text(f"📡 {account_name}/{region} ({completed}/{total})")
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

if st.session_state.get('alarms_fetch_clicked', False):
    if not account_ids or not regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.alarms_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning CloudWatch alarms..."):
            data, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
            st.session_state.alarms_data = data
            st.session_state.alarms_errors = errors
            st.session_state.alarms_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if data:
            st.success(f"✅ Found {len(data)} alarms in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No alarms found in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.alarms_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.alarms_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.alarms_errors:
            st.write(error)

if st.session_state.alarms_data is not None:
    df = pd.DataFrame(st.session_state.alarms_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.alarms_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.alarms_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                data, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
                st.session_state.alarms_data = data
                st.session_state.alarms_errors = errors
                st.session_state.alarms_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed ({len(data)} alarms in {elapsed:.2f}s)")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df.empty:
        st.info("ℹ️ No alarms found.")
    else:
        # ==================== METRICS ====================
        st.subheader("📊 Summary")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        alarm_count = len(df[df['State'] == 'ALARM'])
        warning_count = len(df[df['State'] == 'INSUFFICIENT_DATA'])
        ok_count = len(df[df['State'] == 'OK'])
        
        with col1:
            st.metric("🔴 Alarms", alarm_count)
        with col2:
            st.metric("🟡 Insufficient Data", warning_count)
        with col3:
            st.metric("🟢 OK", ok_count)
        with col4:
            st.metric("Total Alarms", len(df))
        with col5:
            st.metric("Regions", df['Region'].nunique())
        
        st.markdown("---")
        
        # ==================== FILTERS ====================
        st.subheader("🔍 Filters")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            accounts_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique()),
                default=sorted(df['Account Name'].unique()),
                key="alarms_account"
            )
        
        with col2:
            regions_filter = st.multiselect(
                "Region:",
                options=sorted(df['Region'].unique()),
                default=sorted(df['Region'].unique()),
                key="alarms_region"
            )
        
        with col3:
            state_filter = st.multiselect(
                "State:",
                options=sorted(df['State'].unique()),
                default=sorted(df['State'].unique()),
                key="alarms_state"
            )
        
        with col4:
            namespace_filter = st.multiselect(
                "Namespace:",
                options=sorted(df['Namespace'].unique()),
                default=sorted(df['Namespace'].unique()),
                key="alarms_namespace"
            )
        
        filtered = df[
            (df['Account Name'].isin(accounts_filter)) &
            (df['Region'].isin(regions_filter)) &
            (df['State'].isin(state_filter)) &
            (df['Namespace'].isin(namespace_filter))
        ]
        
        st.markdown("---")
        
        # ==================== OVERVIEW GRAPHS ====================
        st.subheader("📈 Overview")
        
        graph_col1, graph_col2 = st.columns(2)
        
        # Alarms by State
        with graph_col1:
            state_counts = filtered['State'].value_counts()
            colors = {'ALARM': '#dc3545', 'OK': '#28a745', 'INSUFFICIENT_DATA': '#ffc107'}
            fig_state = px.pie(
                values=state_counts.values,
                names=state_counts.index,
                title="Alarms by State",
                hole=0.3,
                color_discrete_map=colors
            )
            st.plotly_chart(fig_state, use_container_width=True)
        
        # Alarms by Namespace
        with graph_col2:
            namespace_counts = filtered['Namespace'].value_counts().head(10)
            fig_namespace = px.bar(
                x=namespace_counts.index,
                y=namespace_counts.values,
                title="Top 10 Namespaces by Alarm Count",
                labels={'x': 'Namespace', 'y': 'Count'}
            )
            fig_namespace.update_traces(marker_color='#1f77b4')
            fig_namespace.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_namespace, use_container_width=True)
        
        graph_col3, graph_col4 = st.columns(2)
        
        # Alarms by Account
        with graph_col3:
            account_counts = filtered['Account Name'].value_counts()
            fig_account = px.bar(
                x=account_counts.index,
                y=account_counts.values,
                title="Alarms by Account",
                labels={'x': 'Account', 'y': 'Count'}
            )
            fig_account.update_traces(marker_color='#ff7f0e')
            st.plotly_chart(fig_account, use_container_width=True)
        
        # Alarms by Region
        with graph_col4:
            region_counts = filtered['Region'].value_counts()
            fig_region = px.bar(
                x=region_counts.index,
                y=region_counts.values,
                title="Alarms by Region",
                labels={'x': 'Region', 'y': 'Count'}
            )
            fig_region.update_traces(marker_color='#2ca02c')
            st.plotly_chart(fig_region, use_container_width=True)
        
        st.markdown("---")
        
        # ==================== TABS ====================
        tab1, tab2, tab3 = st.tabs(["📋 All Alarms", "🔴 Triggered Alarms", "⏰ Recently Changed"])
        
        # TAB 1: ALL ALARMS
        with tab1:
            st.subheader("All CloudWatch Alarms")
            
            display_cols = [
                'Alarm Name', 'State', 'In Alarm Since', 'Namespace', 'Metric Name',
                'Threshold', 'Comparison', 'Statistic', 'Account Name', 'Region'
            ]
            
            display_df = filtered[display_cols].sort_values('State')
            
            # Color code by state
            def highlight_state(row):
                state = row['State']
                if state == 'ALARM':
                    return ['background-color: #f8d7da'] * len(row)
                elif state == 'INSUFFICIENT_DATA':
                    return ['background-color: #fff3cd'] * len(row)
                else:
                    return ['background-color: #d4edda'] * len(row)
            
            st.dataframe(
                display_df.style.apply(highlight_state, axis=1),
                use_container_width=True,
                height=500
            )
            
            csv = display_df.to_csv(index=False)
            st.download_button(
                label="📥 Download All Alarms CSV",
                data=csv,
                file_name=f"alarms_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        # TAB 2: TRIGGERED ALARMS
        with tab2:
            st.subheader("Triggered Alarms (State: ALARM)")
            triggered = filtered[filtered['State'] == 'ALARM']
            
            if triggered.empty:
                st.success("✅ No triggered alarms!")
            else:
                st.metric("🔴 Active Alarms", len(triggered))
                
                display_cols = [
                    'Alarm Name', 'In Alarm Since', 'Description', 'Namespace', 'Metric Name',
                    'Current Value', 'Threshold', 'Account Name', 'Region'
                ]
                
                # Only show columns that exist
                display_cols = [col for col in display_cols if col in triggered.columns or col in ['Alarm Name', 'In Alarm Since', 'Description', 'Namespace', 'Metric Name', 'Threshold', 'Account Name', 'Region']]
                
                display_df = triggered[['Alarm Name', 'In Alarm Since', 'Description', 'Namespace', 'Metric Name', 'Threshold', 'Account Name', 'Region']].sort_values('Alarm Name')
                
                st.dataframe(
                    display_df.style.apply(lambda row: ['background-color: #f8d7da'] * len(row), axis=1),
                    use_container_width=True,
                    height=500
                )
                
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Triggered Alarms CSV",
                    data=csv,
                    file_name=f"alarms_triggered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        # TAB 3: RECENTLY CHANGED
        with tab3:
            st.subheader("Recently Changed Alarms (Last 24 hours)")
            
            # Parse state updated timestamp and filter last 24 hours
            df_copy = filtered.copy()
            try:
                df_copy['StateUpdatedTimestamp'] = pd.to_datetime(df_copy['State Updated'])
                cutoff = datetime.now(df_copy['StateUpdatedTimestamp'].dt.tz[0]) - timedelta(hours=24)
                recent = df_copy[df_copy['StateUpdatedTimestamp'] >= cutoff].sort_values('StateUpdatedTimestamp', ascending=False)
            except:
                recent = df_copy.sort_values('State Updated', ascending=False).head(50)
            
            if recent.empty:
                st.info("ℹ️ No alarms changed in the last 24 hours")
            else:
                st.metric("⏰ Recently Changed", len(recent))
                
                display_cols = [
                    'Alarm Name', 'State', 'State Updated', 'Description', 'Namespace', 
                    'Account Name', 'Region'
                ]
                
                display_df = recent[display_cols]
                
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    height=500
                )
                
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Recently Changed CSV",
                    data=csv,
                    file_name=f"alarms_recent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
