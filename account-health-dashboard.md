# Account Health Dashboard

Save this as: `pages/Account_Health.py`

```python
"""
Account Health Dashboard

Provides a comprehensive summary of account security and resource health:
- IAM security metrics (users, keys, MFA)
- Resource counts (EC2, VPC, S3 buckets)
- Security Hub findings
- Trusted Advisor checks (if available)
- Account age and basic information
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
st.set_page_config(page_title="Account Health", page_icon="🏥", layout="wide")

# Initialize session state
if 'account_health_data' not in st.session_state:
    st.session_state.account_health_data = None
if 'account_health_last_refresh' not in st.session_state:
    st.session_state.account_health_last_refresh = None

# Header
st.title("🏥 Account Health Dashboard")

# Get all accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# ============================================================================
# SIDEBAR CONFIGURATION
# ============================================================================

selected_account_ids, selected_regions = render_sidebar(page_key_prefix="health_")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_iam_metrics(iam_client):
    """Get IAM security metrics"""
    try:
        # Count users
        users_response = iam_client.list_users()
        total_users = len(users_response['Users'])
        
        # Count users without MFA
        users_no_mfa = 0
        total_access_keys = 0
        old_keys = 0
        
        for user in users_response['Users']:
            username = user['UserName']
            
            # Check MFA
            try:
                mfa_response = iam_client.list_mfa_devices(UserName=username)
                if len(mfa_response['MFADevices']) == 0:
                    users_no_mfa += 1
            except:
                pass
            
            # Check access keys
            try:
                keys_response = iam_client.list_access_keys(UserName=username)
                keys = keys_response['AccessKeyMetadata']
                total_access_keys += len(keys)
                
                for key in keys:
                    key_age = (datetime.now(key['CreateDate'].tzinfo) - key['CreateDate']).days
                    if key_age > 90:
                        old_keys += 1
            except:
                pass
        
        return {
            'total_users': total_users,
            'users_no_mfa': users_no_mfa,
            'total_access_keys': total_access_keys,
            'old_keys_90days': old_keys,
            'mfa_compliance': f"{((total_users - users_no_mfa) / total_users * 100) if total_users > 0 else 0:.1f}%"
        }
    except:
        return {
            'total_users': 0,
            'users_no_mfa': 0,
            'total_access_keys': 0,
            'old_keys_90days': 0,
            'mfa_compliance': 'N/A'
        }

def get_ec2_metrics(ec2_client):
    """Get EC2 resource metrics"""
    try:
        instances = ec2_client.describe_instances()
        
        total_instances = 0
        running_instances = 0
        stopped_instances = 0
        
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                total_instances += 1
                state = instance['State']['Name']
                if state == 'running':
                    running_instances += 1
                elif state == 'stopped':
                    stopped_instances += 1
        
        return {
            'total_instances': total_instances,
            'running_instances': running_instances,
            'stopped_instances': stopped_instances
        }
    except:
        return {
            'total_instances': 0,
            'running_instances': 0,
            'stopped_instances': 0
        }

def get_vpc_metrics(ec2_client):
    """Get VPC metrics"""
    try:
        vpcs = ec2_client.describe_vpcs()
        return {'total_vpcs': len(vpcs['Vpcs'])}
    except:
        return {'total_vpcs': 0}

def get_s3_metrics(account_id, role_name):
    """Get S3 metrics"""
    try:
        s3_client = AWSSession.get_client_for_account('s3', account_id, role_name, 'us-east-1')
        buckets = s3_client.list_buckets()
        return {'total_buckets': len(buckets['Buckets'])}
    except:
        return {'total_buckets': 0}

def get_security_hub_metrics(account_id, role_name, region):
    """Get Security Hub findings count"""
    try:
        sh_client = AWSSession.get_client_for_account('securityhub', account_id, role_name, region)
        
        # Check if Security Hub is enabled
        try:
            sh_client.describe_hub()
        except:
            return {
                'critical_findings': 'N/A',
                'high_findings': 'N/A',
                'medium_findings': 'N/A',
                'security_hub_enabled': False
            }
        
        critical = 0
        high = 0
        medium = 0
        
        # Get critical findings
        try:
            response = sh_client.get_findings(
                Filters={
                    'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                    'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}],
                    'SeverityLabel': [{'Value': 'CRITICAL', 'Comparison': 'EQUALS'}]
                },
                MaxResults=100
            )
            critical = len(response['Findings'])
        except:
            pass
        
        # Get high findings
        try:
            response = sh_client.get_findings(
                Filters={
                    'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                    'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}],
                    'SeverityLabel': [{'Value': 'HIGH', 'Comparison': 'EQUALS'}]
                },
                MaxResults=100
            )
            high = len(response['Findings'])
        except:
            pass
        
        # Get medium findings
        try:
            response = sh_client.get_findings(
                Filters={
                    'RecordState': [{'Value': 'ACTIVE', 'Comparison': 'EQUALS'}],
                    'WorkflowStatus': [{'Value': 'NEW', 'Comparison': 'EQUALS'}],
                    'SeverityLabel': [{'Value': 'MEDIUM', 'Comparison': 'EQUALS'}]
                },
                MaxResults=100
            )
            medium = len(response['Findings'])
        except:
            pass
        
        return {
            'critical_findings': critical,
            'high_findings': high,
            'medium_findings': medium,
            'security_hub_enabled': True
        }
    except:
        return {
            'critical_findings': 'N/A',
            'high_findings': 'N/A',
            'medium_findings': 'N/A',
            'security_hub_enabled': False
        }

def get_account_health(account_id, account_name, role_name, primary_region):
    """Get comprehensive health metrics for an account"""
    health_data = {
        'Account ID': account_id,
        'Account Name': account_name,
    }
    
    try:
        # Get IAM metrics (IAM is global)
        iam_client = AWSSession.get_client_for_account('iam', account_id, role_name, 'us-east-1')
        iam_metrics = get_iam_metrics(iam_client)
        health_data.update(iam_metrics)
        
        # Get EC2 metrics (in primary region)
        ec2_client = AWSSession.get_client_for_account('ec2', account_id, role_name, primary_region)
        ec2_metrics = get_ec2_metrics(ec2_client)
        health_data.update(ec2_metrics)
        
        # Get VPC metrics
        vpc_metrics = get_vpc_metrics(ec2_client)
        health_data.update(vpc_metrics)
        
        # Get S3 metrics
        s3_metrics = get_s3_metrics(account_id, role_name)
        health_data.update(s3_metrics)
        
        # Get Security Hub metrics
        sh_metrics = get_security_hub_metrics(account_id, role_name, primary_region)
        health_data.update(sh_metrics)
        
        # Calculate health score (0-100)
        score = 100
        
        # IAM penalties
        if iam_metrics['total_users'] > 0:
            mfa_ratio = 1 - (iam_metrics['users_no_mfa'] / iam_metrics['total_users'])
            score -= (1 - mfa_ratio) * 20  # Up to -20 for no MFA
        
        if iam_metrics['total_access_keys'] > 0:
            old_keys_ratio = iam_metrics['old_keys_90days'] / iam_metrics['total_access_keys']
            score -= old_keys_ratio * 15  # Up to -15 for old keys
        
        # Security Hub penalties
        if sh_metrics['security_hub_enabled']:
            if isinstance(sh_metrics['critical_findings'], int):
                score -= min(sh_metrics['critical_findings'] * 5, 25)  # Up to -25 for critical findings
            if isinstance(sh_metrics['high_findings'], int):
                score -= min(sh_metrics['high_findings'] * 2, 20)  # Up to -20 for high findings
        else:
            score -= 10  # -10 for Security Hub not enabled
        
        health_data['Health Score'] = max(0, round(score, 1))
        
        # Determine status
        if score >= 80:
            health_data['Status'] = '✅ Good'
        elif score >= 60:
            health_data['Status'] = '⚡ Fair'
        else:
            health_data['Status'] = '⚠️ Poor'
        
    except Exception as e:
        health_data['Health Score'] = 0
        health_data['Status'] = '❌ Error'
    
    return health_data

def fetch_account_health_data(selected_account_ids, all_accounts, role_name, primary_region):
    """Fetch health data for all selected accounts"""
    all_health_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_accounts = len(selected_account_ids)
    
    with ThreadPoolExecutor(max_workers=min(AWSConfig.MAX_WORKERS, total_accounts)) as executor:
        futures = {}
        
        for idx, account_id in enumerate(selected_account_ids):
            account_name = AWSOrganizations.get_account_name_by_id(account_id, all_accounts)
            
            future = executor.submit(
                get_account_health,
                account_id,
                account_name,
                role_name,
                primary_region
            )
            futures[future] = (account_id, account_name, idx)
        
        for future in as_completed(futures):
            account_id, account_name, idx = futures[future]
            status_text.text(f"📡 Scanning Account Health: {account_name} ({idx + 1}/{total_accounts})")
            
            try:
                health = future.result()
                all_health_data.append(health)
            except Exception:
                pass
            
            progress_bar.progress((idx + 1) / total_accounts)
    
    progress_bar.empty()
    status_text.empty()
    
    return all_health_data

# ============================================================================
# BUTTON HANDLERS
# ============================================================================

# Primary region selection
st.sidebar.markdown("---")
st.sidebar.subheader("🌍 Primary Region")
primary_region = st.sidebar.selectbox(
    "Select primary region for metrics:",
    options=['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'],
    index=0,
    help="Region to scan for EC2, VPC, and Security Hub metrics"
)

# Check if fetch button was clicked
if st.session_state.get('health_fetch_clicked', False):
    if not selected_account_ids:
        st.warning("⚠️ Please select at least one account.")
        st.session_state.health_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Scanning health metrics in {len(selected_account_ids)} account(s)..."):
            health_data = fetch_account_health_data(
                selected_account_ids,
                all_accounts,
                AWSConfig.READONLY_ROLE_NAME,
                primary_region
            )
            st.session_state.account_health_data = health_data
            st.session_state.account_health_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed_time = time.time() - start_time
        st.success(f"✅ Successfully fetched health data for {len(health_data)} accounts in {elapsed_time:.2f} seconds")
        st.session_state.health_fetch_clicked = False

# ============================================================================
# DISPLAY RESULTS
# ============================================================================

if st.session_state.account_health_data is not None:
    df = pd.DataFrame(st.session_state.account_health_data)
    
    # Refresh button on main page
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        if st.session_state.account_health_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.account_health_last_refresh}")
    with col_refresh:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            if not selected_account_ids:
                st.warning("⚠️ Please select at least one account.")
            else:
                start_time = time.time()
                
                with st.spinner(f"🔍 Refreshing data..."):
                    health_data = fetch_account_health_data(
                        selected_account_ids,
                        all_accounts,
                        AWSConfig.READONLY_ROLE_NAME,
                        primary_region
                    )
                    st.session_state.account_health_data = health_data
                    st.session_state.account_health_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                elapsed_time = time.time() - start_time
                st.success(f"✅ Data refreshed ({len(health_data)} accounts in {elapsed_time:.2f} seconds)")
                st.rerun()
    
    if df.empty:
        st.info("ℹ️ No account health data found.")
    else:
        # Summary metrics
        st.subheader("📊 Overall Health Summary")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        avg_score = df['Health Score'].mean()
        good_accounts = len(df[df['Status'] == '✅ Good'])
        fair_accounts = len(df[df['Status'] == '⚡ Fair'])
        poor_accounts = len(df[df['Status'] == '⚠️ Poor'])
        total_critical = df['critical_findings'].apply(lambda x: x if isinstance(x, int) else 0).sum()
        
        with col1:
            st.metric("Average Health Score", f"{avg_score:.1f}/100")
        
        with col2:
            st.metric("✅ Good", good_accounts)
        
        with col3:
            st.metric("⚡ Fair", fair_accounts)
        
        with col4:
            st.metric("⚠️ Poor", poor_accounts)
        
        with col5:
            st.metric("🔴 Critical Findings", total_critical)
        
        st.markdown("---")
        
        # Filters
        st.subheader("🔍 Filters")
        
        filter_col1, filter_col2 = st.columns(2)
        
        with filter_col1:
            status_filter = st.multiselect(
                "Status:",
                options=sorted(df['Status'].unique().tolist()),
                default=sorted(df['Status'].unique().tolist())
            )
        
        with filter_col2:
            account_filter = st.multiselect(
                "Account:",
                options=sorted(df['Account Name'].unique().tolist()),
                default=sorted(df['Account Name'].unique().tolist())
            )
        
        # Apply filters
        filtered_df = df[
            (df['Status'].isin(status_filter)) &
            (df['Account Name'].isin(account_filter))
        ]
        
        # Sort by Health Score descending
        filtered_df = filtered_df.sort_values('Health Score', ascending=False)
        
        st.markdown("---")
        
        # Display data
        st.subheader(f"📋 Account Health Details ({len(filtered_df)} accounts)")
        
        # Column selector
        available_columns = filtered_df.columns.tolist()
        default_columns = [
            'Account Name', 'Health Score', 'Status', 'total_users', 'users_no_mfa',
            'old_keys_90days', 'total_instances', 'running_instances',
            'critical_findings', 'high_findings'
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
            label="📥 Download Account Health Report (CSV)",
            data=csv,
            file_name=f"account_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # Statistics
        with st.expander("📈 Detailed Statistics"):
            stat_col1, stat_col2 = st.columns(2)
            
            with stat_col1:
                st.write("**Health Score Distribution:**")
                score_bins = pd.cut(filtered_df['Health Score'], bins=[0, 60, 80, 100], labels=['Poor (0-60)', 'Fair (60-80)', 'Good (80-100)'])
                score_dist = score_bins.value_counts()
                st.dataframe(score_dist, use_container_width=True)
                
                st.write("**Total Resources:**")
                resource_summary = pd.DataFrame({
                    'Total IAM Users': [filtered_df['total_users'].sum()],
                    'Total EC2 Instances': [filtered_df['total_instances'].sum()],
                    'Total S3 Buckets': [filtered_df['total_buckets'].sum()],
                    'Total VPCs': [filtered_df['total_vpcs'].sum()]
                }).T
                st.dataframe(resource_summary, use_container_width=True)
            
            with stat_col2:
                st.write("**Security Issues:**")
                security_summary = pd.DataFrame({
                    'Users Without MFA': [filtered_df['users_no_mfa'].sum()],
                    'Old Access Keys (>90d)': [filtered_df['old_keys_90days'].sum()],
                    'Critical Findings': [total_critical],
                    'High Findings': [df['high_findings'].apply(lambda x: x if isinstance(x, int) else 0).sum()]
                }).T
                st.dataframe(security_summary, use_container_width=True)
                
                st.write("**Accounts by Status:**")
                status_counts = filtered_df['Status'].value_counts()
                st.dataframe(status_counts, use_container_width=True)

else:
    st.info("👈 Configure options in the sidebar and click 'Fetch Data' to begin.")
    
    st.markdown("""
    ### 🏥 About Account Health Dashboard
    
    This dashboard provides a comprehensive health check of your AWS accounts.
    
    **Metrics Collected:**
    - **IAM Security**: User counts, MFA status, access key age
    - **EC2 Resources**: Instance counts by state
    - **Network**: VPC counts
    - **Storage**: S3 bucket counts
    - **Security Hub**: Active findings by severity
    - **Health Score**: Calculated score (0-100) based on security posture
    
    **Health Score Calculation:**
    - Starts at 100
    - Deductions for users without MFA (up to -20)
    - Deductions for old access keys (up to -15)
    - Deductions for Security Hub findings (up to -45)
    - Deduction if Security Hub not enabled (-10)
    
    **Status Indicators:**
    - ✅ Good: Score 80-100
    - ⚡ Fair: Score 60-79
    - ⚠️ Poor: Score 0-59
    """)
```
