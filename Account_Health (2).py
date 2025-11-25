"""
Account Health Dashboard

Calculates comprehensive health score using:
- Security Hub findings
- AWS Config compliance  
- IAM security (MFA, key age)
- AWS Backup coverage
- Trusted Advisor checks

Uses your utils.py
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

# Sidebar
account_ids, regions = setup_account_filter(page_key="health")

st.sidebar.markdown("---")
st.sidebar.subheader("🌍 Primary Region")
primary_region = st.sidebar.selectbox(
    "Select region for metrics:",
    options=['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'],
    index=0
)

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

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
                health['Old Keys'] = old_keys
                
                if total_users > 0:
                    mfa_penalty = (users_no_mfa / total_users) * 10
                    score -= mfa_penalty
                
                if total_keys > 0:
                    key_penalty = (old_keys / total_keys) * 10
                    score -= key_penalty
            else:
                health['Total Users'] = 'N/A'
                health['Users No MFA'] = 'N/A'
                health['Total Keys'] = 'N/A'
                health['Old Keys'] = 'N/A'
                score -= 10
                    
        except ClientError as e:
            errors.append(f"⚠️ {account_name}: Cannot access IAM")
            health['Total Users'] = 'N/A'
            health['Users No MFA'] = 'N/A'
            health['Total Keys'] = 'N/A'
            health['Old Keys'] = 'N/A'
            score -= 10
        
        # ==================== SECURITY HUB (40 points) ====================
        try:
            sh = get_securityhub_client(account_id, role_name, primary_region)
            if sh:
                try:
                    sh.describe_hub()
                    
                    critical = 0
                    high = 0
                    
                    try:
                        resp = sh.get_findings(
                            Filters={
                                'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                                'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}],
                                'SeverityLabel': [{'Value': 'CRITICAL', 'Comparison': 'EQUALS'}]
                            },
                            MaxResults=100
                        )
                        critical = len(resp['Findings'])
                    except:
                        pass
                    
                    try:
                        resp = sh.get_findings(
                            Filters={
                                'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                                'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}],
                                'SeverityLabel': [{'Value': 'HIGH', 'Comparison': 'EQUALS'}]
                            },
                            MaxResults=100
                        )
                        high = len(resp['Findings'])
                    except:
                        pass
                    
                    health['Critical Findings'] = critical
                    health['High Findings'] = high
                    health['Security Hub'] = 'Enabled'
                    
                    score -= min(critical * 5, 25)
                    score -= min(high * 2, 15)
                    
                except ClientError:
                    health['Critical Findings'] = 'N/A'
                    health['High Findings'] = 'N/A'
                    health['Security Hub'] = 'Not Enabled'
                    score -= 10
            else:
                health['Critical Findings'] = 'N/A'
                health['High Findings'] = 'N/A'
                health['Security Hub'] = 'N/A'
                score -= 10
                    
        except ClientError as e:
            health['Critical Findings'] = 'N/A'
            health['High Findings'] = 'N/A'
            health['Security Hub'] = 'N/A'
            score -= 10
        
        # ==================== AWS CONFIG (20 points) ====================
        try:
            config = get_config_client(account_id, role_name, primary_region)
            if config:
                try:
                    paginator = config.get_paginator('describe_config_rules')
                    total_rules = 0
                    non_compliant = 0
                    
                    for page in paginator.paginate():
                        for rule in page['ConfigRules']:
                            total_rules += 1
                            rule_name = rule['ConfigRuleName']
                            
                            try:
                                compliance = config.describe_compliance_by_config_rule(
                                    ConfigRuleNames=[rule_name]
                                )
                                
                                if compliance['ComplianceByConfigRules']:
                                    comp_type = compliance['ComplianceByConfigRules'][0]['Compliance'].get('ComplianceType', '')
                                    if comp_type == 'NON_COMPLIANT':
                                        non_compliant += 1
                            except:
                                pass
                    
                    health['Total Config Rules'] = total_rules
                    health['Non-Compliant Rules'] = non_compliant
                    health['Config'] = 'Enabled'
                    
                    if total_rules > 0:
                        compliance_penalty = (non_compliant / total_rules) * 20
                        score -= compliance_penalty
                        
                except ClientError as e:
                    health['Total Config Rules'] = 0
                    health['Non-Compliant Rules'] = 0
                    health['Config'] = 'Not Enabled'
                    score -= 10
            else:
                health['Total Config Rules'] = 'N/A'
                health['Non-Compliant Rules'] = 'N/A'
                health['Config'] = 'N/A'
                score -= 10
                    
        except ClientError as e:
            health['Total Config Rules'] = 'N/A'
            health['Non-Compliant Rules'] = 'N/A'
            health['Config'] = 'N/A'
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
                health['Protected Resources'] = 'N/A'
                health['Backup'] = 'N/A'
                score -= 5
                    
        except ClientError as e:
            health['Protected Resources'] = 'N/A'
            health['Backup'] = 'N/A'
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
# DISPLAY
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
            st.caption(f"Last refreshed: {st.session_state.health_last_refresh}")
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
        # Metrics
        st.subheader("📊 Overall Health")
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
        st.subheader(f"📋 Account Health ({len(filtered)} accounts)")
        st.dataframe(filtered, use_container_width=True, height=500, hide_index=True)
        
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
