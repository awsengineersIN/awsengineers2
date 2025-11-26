"""
Billing Dashboard

Features:
- Filter by multiple accounts
- Current month total, estimated month-end total, average daily cost
- Top 10 services by cost
- Pie chart with service cost breakdown
- Line graph of daily cost trends

Uses your utils.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
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

# Page configuration
st.set_page_config(page_title="Billing", page_icon="💰", layout="wide")

# Initialize session state
if 'billing_data' not in st.session_state:
    st.session_state.billing_data = None
if 'billing_daily_data' not in st.session_state:
    st.session_state.billing_daily_data = None
if 'billing_last_refresh' not in st.session_state:
    st.session_state.billing_last_refresh = None
if 'billing_errors' not in st.session_state:
    st.session_state.billing_errors = []

st.title("💰 Billing Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="billing")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_ce_client(account_id, role_name):
    """Get Cost Explorer client"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'ce',
        region_name='us-east-1',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_billing_data(account_id, account_name, role_name):
    """Get billing data for current month"""
    services_data = []
    daily_data = []
    errors = []
    
    try:
        ce_client = get_ce_client(account_id, role_name)
        if not ce_client:
            errors.append(f"❌ {account_name}: Failed to get Cost Explorer client")
            return services_data, daily_data, errors
        
        # Get current month dates
        today = datetime.now()
        current_month_start = today.replace(day=1)
        
        # Calculate estimated month end
        if today.month == 12:
            month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        
        # ==================== GET SERVICE-LEVEL COSTS ====================
        try:
            response = ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': current_month_start.strftime('%Y-%m-%d'),
                    'End': today.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'}
                ]
            )
            
            current_month_total = 0
            
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service_name = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    current_month_total += cost
                    
                    services_data.append({
                        'Account ID': account_id,
                        'Account Name': account_name,
                        'Service': service_name,
                        'Cost': cost
                    })
            
            # Calculate average daily cost
            days_in_month = (today - current_month_start).days + 1
            avg_daily_cost = current_month_total / days_in_month if days_in_month > 0 else 0
            
            # Calculate estimated month-end cost
            total_days_in_month = (month_end - current_month_start).days + 1
            estimated_month_end = (current_month_total / days_in_month) * total_days_in_month if days_in_month > 0 else 0
            
            # Store summary in first row for easy access
            if services_data:
                services_data[0]['Current Month Total'] = current_month_total
                services_data[0]['Estimated Month End'] = estimated_month_end
                services_data[0]['Average Daily Cost'] = avg_daily_cost
            else:
                # Add summary row even if no services
                services_data.append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Service': 'No Cost Data',
                    'Cost': 0,
                    'Current Month Total': current_month_total,
                    'Estimated Month End': estimated_month_end,
                    'Average Daily Cost': avg_daily_cost
                })
                
        except ClientError as e:
            errors.append(f"⚠️ {account_name}: Error fetching service costs - {str(e)}")
        
        # ==================== GET DAILY COST TRENDS ====================
        try:
            response = ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': current_month_start.strftime('%Y-%m-%d'),
                    'End': today.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            
            for result in response['ResultsByTime']:
                date = result['TimePeriod']['Start']
                cost = float(result['Total']['UnblendedCost']['Amount'])
                
                daily_data.append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Date': date,
                    'Cost': cost
                })
                
        except ClientError as e:
            errors.append(f"⚠️ {account_name}: Error fetching daily costs - {str(e)}")
        
    except Exception as e:
        errors.append(f"❌ {account_name}: Unexpected error - {str(e)}")
    
    return services_data, daily_data, errors

def fetch_data(account_ids, all_accounts, role_name):
    """Fetch billing data with parallel processing"""
    all_services = []
    all_daily = []
    all_errors = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(account_ids)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        
        for account_id in account_ids:
            account_name = get_account_name_by_id(account_id, all_accounts)
            future = executor.submit(get_billing_data, account_id, account_name, role_name)
            futures[future] = (account_id, account_name)
        
        for future in as_completed(futures):
            account_id, account_name = futures[future]
            completed += 1
            status_text.text(f"📡 {account_name} ({completed}/{total})")
            progress_bar.progress(completed / total)
            
            try:
                services, daily, errors = future.result()
                all_services.extend(services)
                all_daily.extend(daily)
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"❌ {account_name}: Failed - {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return all_services, all_daily, all_errors

# ============================================================================
# FETCH BUTTON
# ============================================================================

if st.session_state.get('billing_fetch_clicked', False):
    if not account_ids:
        st.warning("⚠️ Please select at least one account.")
        st.session_state.billing_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Fetching billing data..."):
            services, daily, errors = fetch_data(account_ids, all_accounts, "readonly-role")
            st.session_state.billing_data = services
            st.session_state.billing_daily_data = daily
            st.session_state.billing_errors = errors
            st.session_state.billing_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        if services:
            st.success(f"✅ Billing data fetched in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No billing data in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.billing_fetch_clicked = False

# ============================================================================
# DISPLAY
# ============================================================================

if debug_mode and st.session_state.billing_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.billing_errors:
            st.write(error)

if st.session_state.billing_data is not None:
    df_services = pd.DataFrame(st.session_state.billing_data)
    df_daily = pd.DataFrame(st.session_state.billing_daily_data)
    
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.billing_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.billing_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                services, daily, errors = fetch_data(account_ids, all_accounts, "readonly-role")
                st.session_state.billing_data = services
                st.session_state.billing_daily_data = daily
                st.session_state.billing_errors = errors
                st.session_state.billing_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed in {elapsed:.2f}s")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    if df_services.empty:
        st.info("ℹ️ No billing data found.")
    else:
        # Filter by account
        st.subheader("🔍 Filters")
        account_filter = st.multiselect(
            "Account:",
            options=sorted(df_services['Account Name'].unique()),
            default=sorted(df_services['Account Name'].unique())
        )
        
        df_filtered = df_services[df_services['Account Name'].isin(account_filter)]
        df_daily_filtered = df_daily[df_daily['Account Name'].isin(account_filter)]
        
        st.markdown("---")
        
        # ==================== METRICS ====================
        st.subheader("💵 Billing Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        # Get summary values from first row
        if len(df_filtered) > 0:
            sample_row = df_filtered.iloc[0]
            current_total = sample_row.get('Current Month Total', 0)
            estimated_end = sample_row.get('Estimated Month End', 0)
            avg_daily = sample_row.get('Average Daily Cost', 0)
        else:
            current_total = 0
            estimated_end = 0
            avg_daily = 0
        
        with col1:
            st.metric("Current Month Total", f"${current_total:,.2f}")
        with col2:
            st.metric("Estimated Month End", f"${estimated_end:,.2f}")
        with col3:
            st.metric("Average Daily Cost", f"${avg_daily:,.2f}")
        with col4:
            num_accounts = len(account_filter)
            st.metric("Accounts", num_accounts)
        
        st.markdown("---")
        
        # ==================== TOP 10 SERVICES TABLE ====================
        st.subheader("📊 Top 10 Services by Cost")
        
        # Group by service and sum costs
        service_costs = df_filtered.groupby('Service')['Cost'].sum().sort_values(ascending=False).head(10)
        
        service_df = pd.DataFrame({
            'Service': service_costs.index,
            'Cost': service_costs.values
        })
        
        service_df['% of Total'] = (service_df['Cost'] / service_df['Cost'].sum() * 100).round(2)
        service_df = service_df.sort_values('Cost', ascending=False)
        
        st.dataframe(service_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # ==================== CHARTS ====================
        st.subheader("📈 Cost Analysis")
        
        col1, col2 = st.columns(2)
        
        # Pie chart
        with col1:
            fig_pie = go.Figure(data=[go.Pie(
                labels=service_df['Service'],
                values=service_df['Cost'],
                hovertemplate='<b>%{label}</b><br>Cost: $%{value:,.2f}<br>%{customdata}%<extra></extra>',
                customdata=service_df['% of Total'].round(2)
            )])
            
            fig_pie.update_layout(
                title="Cost Distribution by Service",
                height=400
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # Line chart for daily trends
        with col2:
            if not df_daily_filtered.empty:
                # Group daily data by date and sum costs
                daily_summary = df_daily_filtered.groupby('Date')['Cost'].sum().reset_index()
                daily_summary = daily_summary.sort_values('Date')
                
                fig_line = go.Figure()
                fig_line.add_trace(go.Scatter(
                    x=daily_summary['Date'],
                    y=daily_summary['Cost'],
                    mode='lines+markers',
                    name='Daily Cost',
                    line=dict(color='#1f77b4', width=2),
                    marker=dict(size=6)
                ))
                
                fig_line.update_layout(
                    title="Daily Cost Trends",
                    xaxis_title="Date",
                    yaxis_title="Cost ($)",
                    hovermode='x unified',
                    height=400
                )
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("No daily data available")
        
        st.markdown("---")
        
        # ==================== DETAILED TABLE ====================
        st.subheader("📋 Detailed Service Costs")
        
        detail_df = df_filtered[['Account Name', 'Service', 'Cost']].copy()
        detail_df = detail_df.sort_values(['Account Name', 'Cost'], ascending=[True, False])
        
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
        
        # Download
        st.markdown("---")
        csv = detail_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"billing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

else:
    st.info("👈 Select accounts, then click 'Fetch Data'")
