"""
Account Health Dashboard - Enhanced with Charts

Calculates comprehensive health score using:
- Security Hub findings
- AWS Config compliance  
- IAM security (MFA, key age)
- AWS Backup coverage

Uses your utils.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import boto3
import plotly.graph_objects as go
import plotly.express as px

from utils import (
    assume_role,
    setup_account_filter,
    get_account_name_by_id,
)
from botocore.exceptions import ClientError

st.set_page_config(page_title="Account Health", page_icon="🏥", layout="wide")

# Initialize session state
if 'health_data' not in st.session_state:
    st.session_state.health_data = None
if 'health_last_refresh' not in st.session_state:
    st.session_state.health_last_refresh = None
if 'health_errors' not in st.session_state:
    st.session_state.health_errors = []

st.title("🏥 Account Health Dashboard")

all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar (no primary region selector)
account_ids, regions = setup_account_filter(page_key="health")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# Use first selected region or default
primary_region = regions[0] if regions else 'us-east-1'

# ============================================================================
# CLIENT HELPERS
# ============================================================================

def get_iam_client(account_id, role_name):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('iam', region_name='us-east-1',
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])

def get_securityhub_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('securityhub', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])

def get_config_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('config', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])

def get_backup_client(account_id, role_name, region):
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    return boto3.client('backup', region_name=region,
                       aws_access_key_id=credentials['AccessKeyId'],
                       aws_secret_access_key=credentials['SecretAccessKey'],
                       aws_session_token=credentials['SessionToken'])

# ============================================================================
# HEALTH CALCULATION
# ============================================================================

def get_account_health(account_id, account_name, role_name, primary_region):
    """Calculate comprehensive health score"""
    health = {
        'Account ID': account_id,
        'Account Name': account_name,
    }
    errors = []
    score = 100
    
    try:
        # ==================== IAM SECURITY (20 points) ====================
        try:
            iam = get_iam_client(account_id, role_name)
            if iam:
                users_resp = iam.list_users()
                total_users = len(users_resp['Users'])
                users_no_mfa = 0
                total_keys = 0
                old_keys = 0
                
                for user in users_resp['Users']:
                    username = user['UserName']
                    
                    try:
                        mfa_resp = iam.list_mfa_devices(UserName=username)
                        if len(mfa_resp['MFADevices']) == 0:
                            users_no_mfa += 1
                    except:
                        pass
                    
                    try:
                        keys_resp = iam.list_access_keys(UserName=username)
                        keys = keys_resp['AccessKeyMetadata']
                        total_keys += len(keys)
                        
                        for key in keys:
                            key_age = (datetime.now(key['CreateDate'].tzinfo) - key['CreateDate']).days
                            if key_age > 90:
                                old_keys += 1
                    except:
                        pass
                
                health['Total Users'] = total_users
                health['Users No MFA'] = users_no_mfa
                health['Total Keys'] = total_keys
                health['Old Keys (>90d)'] = old_keys
                
                if total_users > 0:
                    mfa_penalty = (users_no_mfa / total_users) * 10
                    score -= mfa_penalty
                
                if total_keys > 0:
                    key_penalty = (old_keys / total_keys) * 10
                    score -= key_penalty
            else:
                health['Total Users'] = 0
                health['Users No MFA'] = 0
                health['Total Keys'] = 0
                health['Old Keys (>90d)'] = 0
                score -= 10
                    
        except ClientError as e:
            errors.append(f"⚠️ {account_name}: Cannot access IAM")
            health['Total Users'] = 0
            health['Users No MFA'] = 0
            health['Total Keys'] = 0
            health['Old Keys (>90d)'] = 0
            score -= 10
        
        # ==================== SECURITY HUB (40 points) ====================
        try:
            sh = get_securityhub_client(account_id, role_name, primary_region)
            if sh:
                try:
                    sh.describe_hub()
                    
                    critical = 0
                    high = 0
                    medium = 0
                    low = 0
                    
                    for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
                        try:
                            resp = sh.get_findings(
                                Filters={
                                    'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                                    'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}],
                                    'SeverityLabel': [{'Value': severity, 'Comparison': 'EQUALS'}]
                                },
                                MaxResults=100
                            )
                            count = len(resp['Findings'])
                            if severity == 'CRITICAL':
                                critical = count
                            elif severity == 'HIGH':
                                high = count
                            elif severity == 'MEDIUM':
                                medium = count
                            elif severity == 'LOW':
                                low = count
                        except:
                            pass
                    
                    health['Critical Findings'] = critical
                    health['High Findings'] = high
                    health['Medium Findings'] = medium
                    health['Low Findings'] = low
                    health['Security Hub'] = 'Enabled'
                    
                    score -= min(critical * 5, 25)
                    score -= min(high * 2, 15)
                    
                except ClientError:
                    health['Critical Findings'] = 0
                    health['High Findings'] = 0
                    health['Medium Findings'] = 0
                    health['Low Findings'] = 0
                    health['Security Hub'] = 'Not Enabled'
                    score -= 10
            else:
                health['Critical Findings'] = 0
                health['High Findings'] = 0
                health['Medium Findings'] = 0
                health['Low Findings'] = 0
                health['Security Hub'] = 'Not Available'
                score -= 10
                    
        except ClientError as e:
            health['Critical Findings'] = 0
            health['High Findings'] = 0
            health['Medium Findings'] = 0
            health['Low Findings'] = 0
            health['Security Hub'] = 'Error'
            score -= 10
        
        # ==================== AWS CONFIG (20 points) ====================
        try:
            config = get_config_client(account_id, role_name, primary_region)
            if config:
                try:
                    paginator = config.get_paginator('describe_config_rules')
                    total_rules = 0
                    compliant = 0
                    non_compliant = 0
                    insufficient = 0
                    
                    for page in paginator.paginate():
                        for rule in page['ConfigRules']:
                            total_rules += 1
                            rule_name = rule['ConfigRuleName']
                            
                            try:
                                compliance = config.describe_compliance_by_config_rule(
                                    ConfigRuleNames=[rule_name]
                                )
                                
                                if compliance['ComplianceByConfigRules']:
                                    comp_type = compliance['ComplianceByConfigRules'][0]['Compliance'].get('ComplianceType', 'INSUFFICIENT_DATA')
                                    if comp_type == 'COMPLIANT':
                                        compliant += 1
                                    elif comp_type == 'NON_COMPLIANT':
                                        non_compliant += 1
                                    else:
                                        insufficient += 1
                            except:
                                insufficient += 1
                    
                    health['Total Config Rules'] = total_rules
                    health['Compliant Rules'] = compliant
                    health['Non-Compliant Rules'] = non_compliant
                    health['Insufficient Data'] = insufficient
                    health['Config'] = 'Enabled'
                    
                    if total_rules > 0:
                        compliance_penalty = (non_compliant / total_rules) * 20
                        score -= compliance_penalty
                        
                except ClientError as e:
                    health['Total Config Rules'] = 0
                    health['Compliant Rules'] = 0
                    health['Non-Compliant Rules'] = 0
                    health['Insufficient Data'] = 0
                    health['Config'] = 'Not Enabled'
                    score -= 10
            else:
                health['Total Config Rules'] = 0
                health['Compliant Rules'] = 0
                health['Non-Compliant Rules'] = 0
                health['Insufficient Data'] = 0
                health['Config'] = 'Not Available'
                score -= 10
                    
        except ClientError as e:
            health['Total Config Rules'] = 0
            health['Compliant Rules'] = 0
            health['Non-Compliant Rules'] = 0
            health['Insufficient Data'] = 0
            health['Config'] = 'Error'
            score -= 10
        
        # ==================== AWS BACKUP (10 points) ====================
        try:
            backup = get_backup_client(account_id, role_name, primary_region)
            if backup:
                try:
                    protected = backup.list_protected_resources(MaxResults=100)
                    protected_count = len(protected.get('Results', []))
                    
                    health['Protected Resources'] = protected_count
                    health['Backup'] = 'Enabled'
                    
                    if protected_count == 0:
                        score -= 10
                    elif protected_count < 5:
                        score -= 5
                        
                except:
                    health['Protected Resources'] = 0
                    health['Backup'] = 'Not Configured'
                    score -= 5
            else:
                health['Protected Resources'] = 0
                health['Backup'] = 'Not Available'
                score -= 5
                    
        except ClientError as e:
            health['Protected Resources'] = 0
            health['Backup'] = 'Error'
            score -= 5
        
        # Final score and status
        health['Health Score'] = max(0, round(score, 1))
        
        if score >= 80:
            health['Status'] = '🟢 Excellent'
        elif score >= 60:
            health['Status'] = '🟡 Good'
        elif score >= 40:
            health['Status'] = '🟠 Fair'
        else:
            health['Status'] = '🔴 Poor'
        
    except Exception as e:
        errors.append(f"❌ {account_name}: Unexpected error - {str(e)}")
        health['Health Score'] = 0
        health['Status'] = '❌ Error'
    
    return health, errors

def fetch_data(account_ids, all_accounts, role_name, primary_region):
    """Fetch data with parallel processing"""
    all_data = []
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(account_ids)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_account = {
            executor.submit(get_account_health, account_id,
                          get_account_name_by_id(account_id, all_accounts),
                          role_name, primary_region): account_id
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
                all_data.append(data)
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"❌ {account_name}: Failed - {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return all_data, all_errors

# ============================================================================
# FETCH BUTTON
# ============================================================================

if st.session_state.get('health_fetch_clicked', False):
    if not account_ids:
        st.warning("⚠️ Please select at least one account.")
        st.session_state.health_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning account health..."):
            data, errors = fetch_data(account_ids, all_accounts, "readonly-role", primary_region)
            st.session_state.health_data = data
            st.session_state.health_errors = errors
            st.session_state.health_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if data:
            st.success(f"✅ Health scan complete for {len(data)} accounts in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No health data in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.health_fetch_clicked = False

# ============================================================================
# DISPLAY WITH CHARTS
# ============================================================================

if debug_mode and st.session_state.health_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.health_errors:
            st.write(error)

if st.session_state.health_data is not None:
    df = pd.DataFrame(st.session_state.health_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.health_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.health_last_refresh} | Region: {primary_region}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                data, errors = fetch_data(account_ids, all_accounts, "readonly-role", primary_region)
                st.session_state.health_data = data
                st.session_state.health_errors = errors
                st.session_state.health_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed ({len(data)} accounts in {elapsed:.2f}s)")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df.empty:
        st.info("ℹ️ No health data found.")
    else:
        # Overall Metrics
        st.subheader("📊 Overall Health Metrics")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        avg_score = df['Health Score'].mean()
        excellent = len(df[df['Status'] == '🟢 Excellent'])
        good = len(df[df['Status'] == '🟡 Good'])
        fair = len(df[df['Status'] == '🟠 Fair'])
        poor = len(df[df['Status'] == '🔴 Poor'])
        
        with col1:
            st.metric("Avg Score", f"{avg_score:.1f}/100")
        with col2:
            st.metric("🟢 Excellent", excellent)
        with col3:
            st.metric("🟡 Good", good)
        with col4:
            st.metric("🟠 Fair", fair)
        with col5:
            st.metric("🔴 Poor", poor)
        
        st.markdown("---")
        
        # Charts Section
        st.subheader("📈 Health Score Distribution")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Health Score Bar Chart
            fig_scores = go.Figure()
            colors = ['#00cc00' if s >= 80 else '#ffcc00' if s >= 60 else '#ff9900' if s >= 40 else '#ff0000' 
                     for s in df['Health Score']]
            
            fig_scores.add_trace(go.Bar(
                x=df['Account Name'],
                y=df['Health Score'],
                marker_color=colors,
                text=df['Health Score'],
                textposition='outside'
            ))
            
            fig_scores.update_layout(
                title="Health Score by Account",
                xaxis_title="Account",
                yaxis_title="Score",
                yaxis_range=[0, 105],
                height=400
            )
            st.plotly_chart(fig_scores, use_container_width=True)
        
        with col2:
            # Status Distribution Pie Chart
            status_counts = df['Status'].value_counts()
            colors_pie = ['#00cc00', '#ffcc00', '#ff9900', '#ff0000']
            
            fig_pie = go.Figure(data=[go.Pie(
                labels=status_counts.index,
                values=status_counts.values,
                marker_colors=colors_pie[:len(status_counts)]
            )])
            
            fig_pie.update_layout(
                title="Account Status Distribution",
                height=400
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        st.markdown("---")
        
        # Security Findings Summary
        st.subheader("🔒 Security Hub Findings Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_critical = df['Critical Findings'].sum()
        total_high = df['High Findings'].sum()
        total_medium = df['Medium Findings'].sum()
        total_low = df['Low Findings'].sum()
        
        with col1:
            st.metric("🔴 Critical", total_critical)
        with col2:
            st.metric("🟠 High", total_high)
        with col3:
            st.metric("🟡 Medium", total_medium)
        with col4:
            st.metric("🟢 Low", total_low)
        
        # Findings by Account Chart
        findings_data = df[['Account Name', 'Critical Findings', 'High Findings', 'Medium Findings', 'Low Findings']]
        
        fig_findings = go.Figure()
        fig_findings.add_trace(go.Bar(name='Critical', x=findings_data['Account Name'], 
                                      y=findings_data['Critical Findings'], marker_color='#ff0000'))
        fig_findings.add_trace(go.Bar(name='High', x=findings_data['Account Name'], 
                                      y=findings_data['High Findings'], marker_color='#ff9900'))
        fig_findings.add_trace(go.Bar(name='Medium', x=findings_data['Account Name'], 
                                      y=findings_data['Medium Findings'], marker_color='#ffcc00'))
        fig_findings.add_trace(go.Bar(name='Low', x=findings_data['Account Name'], 
                                      y=findings_data['Low Findings'], marker_color='#00cc00'))
        
        fig_findings.update_layout(
            title="Security Hub Findings by Account",
            xaxis_title="Account",
            yaxis_title="Number of Findings",
            barmode='group',
            height=400
        )
        st.plotly_chart(fig_findings, use_container_width=True)
        
        st.markdown("---")
        
        # Config Compliance Summary
        st.subheader("⚙️ AWS Config Compliance Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_rules = df['Total Config Rules'].sum()
        total_compliant = df['Compliant Rules'].sum()
        total_noncompliant = df['Non-Compliant Rules'].sum()
        total_insufficient = df['Insufficient Data'].sum()
        
        with col1:
            st.metric("Total Rules", total_rules)
        with col2:
            st.metric("✅ Compliant", total_compliant)
        with col3:
            st.metric("❌ Non-Compliant", total_noncompliant)
        with col4:
            st.metric("⚠️ Insufficient", total_insufficient)
        
        # Config Compliance Chart
        config_data = df[['Account Name', 'Compliant Rules', 'Non-Compliant Rules', 'Insufficient Data']]
        
        fig_config = go.Figure()
        fig_config.add_trace(go.Bar(name='Compliant', x=config_data['Account Name'], 
                                    y=config_data['Compliant Rules'], marker_color='#00cc00'))
        fig_config.add_trace(go.Bar(name='Non-Compliant', x=config_data['Account Name'], 
                                    y=config_data['Non-Compliant Rules'], marker_color='#ff0000'))
        fig_config.add_trace(go.Bar(name='Insufficient', x=config_data['Account Name'], 
                                    y=config_data['Insufficient Data'], marker_color='#cccccc'))
        
        fig_config.update_layout(
            title="Config Compliance by Account",
            xaxis_title="Account",
            yaxis_title="Number of Rules",
            barmode='stack',
            height=400
        )
        st.plotly_chart(fig_config, use_container_width=True)
        
        st.markdown("---")
        
        # IAM Security Summary
        st.subheader("👥 IAM Security Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_users = df['Total Users'].sum()
        total_no_mfa = df['Users No MFA'].sum()
        total_keys = df['Total Keys'].sum()
        total_old_keys = df['Old Keys (>90d)'].sum()
        
        with col1:
            st.metric("Total Users", total_users)
        with col2:
            st.metric("❌ No MFA", total_no_mfa)
        with col3:
            st.metric("Total Keys", total_keys)
        with col4:
            st.metric("🔴 Old Keys", total_old_keys)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # MFA Status Chart
            iam_mfa = df[['Account Name', 'Total Users', 'Users No MFA']].copy()
            iam_mfa['Users With MFA'] = iam_mfa['Total Users'] - iam_mfa['Users No MFA']
            
            fig_mfa = go.Figure()
            fig_mfa.add_trace(go.Bar(name='With MFA', x=iam_mfa['Account Name'], 
                                     y=iam_mfa['Users With MFA'], marker_color='#00cc00'))
            fig_mfa.add_trace(go.Bar(name='No MFA', x=iam_mfa['Account Name'], 
                                     y=iam_mfa['Users No MFA'], marker_color='#ff0000'))
            
            fig_mfa.update_layout(
                title="MFA Status by Account",
                xaxis_title="Account",
                yaxis_title="Number of Users",
                barmode='stack',
                height=400
            )
            st.plotly_chart(fig_mfa, use_container_width=True)
        
        with col2:
            # Key Age Chart
            iam_keys = df[['Account Name', 'Total Keys', 'Old Keys (>90d)']].copy()
            iam_keys['Good Keys'] = iam_keys['Total Keys'] - iam_keys['Old Keys (>90d)']
            
            fig_keys = go.Figure()
            fig_keys.add_trace(go.Bar(name='Good Keys', x=iam_keys['Account Name'], 
                                      y=iam_keys['Good Keys'], marker_color='#00cc00'))
            fig_keys.add_trace(go.Bar(name='Old Keys', x=iam_keys['Account Name'], 
                                      y=iam_keys['Old Keys (>90d)'], marker_color='#ff0000'))
            
            fig_keys.update_layout(
                title="Access Key Age by Account",
                xaxis_title="Account",
                yaxis_title="Number of Keys",
                barmode='stack',
                height=400
            )
            st.plotly_chart(fig_keys, use_container_width=True)
        
        st.markdown("---")
        
        # Backup Summary
        st.subheader("💾 AWS Backup Summary")
        
        total_protected = df['Protected Resources'].sum()
        st.metric("Total Protected Resources", total_protected)
        
        fig_backup = go.Figure()
        fig_backup.add_trace(go.Bar(
            x=df['Account Name'],
            y=df['Protected Resources'],
            marker_color='#00cc00',
            text=df['Protected Resources'],
            textposition='outside'
        ))
        
        fig_backup.update_layout(
            title="Protected Resources by Account",
            xaxis_title="Account",
            yaxis_title="Number of Resources",
            height=400
        )
        st.plotly_chart(fig_backup, use_container_width=True)
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        col1, col2 = st.columns(2)
        
        with col1:
            status = st.multiselect(
                "Status:",
                options=sorted(df['Status'].unique()),
                default=sorted(df['Status'].unique())
            )
        
        with col2:
            accounts = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique()),
                default=sorted(df['Account Name'].unique())
            )
        
        filtered = df[(df['Status'].isin(status)) & (df['Account Name'].isin(accounts))]
        filtered = filtered.sort_values('Health Score', ascending=False)
        
        st.markdown("---")
        
        # Data table
        st.subheader(f"📋 Detailed Account Health ({len(filtered)} accounts)")
        
        # Select columns to display
        display_cols = [
            'Account Name', 'Health Score', 'Status',
            'Critical Findings', 'High Findings', 'Medium Findings', 'Low Findings',
            'Total Config Rules', 'Compliant Rules', 'Non-Compliant Rules',
            'Total Users', 'Users No MFA', 'Total Keys', 'Old Keys (>90d)',
            'Protected Resources', 'Security Hub', 'Config', 'Backup'
        ]
        
        st.dataframe(filtered[display_cols], use_container_width=True, height=400, hide_index=True)
        
        # Download
        st.markdown("---")
        csv = filtered.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"account_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # Score breakdown
        with st.expander("📊 Health Score Breakdown"):
            st.markdown("""
            **Health Score Components (0-100):**
            
            1. **Security Hub (40 points)**
               - Critical findings: -5 points each (max -25)
               - High findings: -2 points each (max -15)
               - Hub not enabled: -10 points
            
            2. **AWS Config (20 points)**
               - Non-compliant rules: up to -20 points based on ratio
               - Config not enabled: -10 points
            
            3. **IAM Security (20 points)**
               - Users without MFA: up to -10 points based on ratio
               - Access keys >90 days: up to -10 points based on ratio
            
            4. **AWS Backup (10 points)**
               - No protected resources: -10 points
               - <5 protected resources: -5 points
            
            **Status Ranges:**
            - 🟢 Excellent: 80-100
            - 🟡 Good: 60-79
            - 🟠 Fair: 40-59
            - 🔴 Poor: 0-39
            """)

else:
    st.info("👈 Select accounts, then click 'Fetch Data'")
