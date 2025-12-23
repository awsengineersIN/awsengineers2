"""
ECS Dashboard - Enhanced with Graphs

Features:
- Filter by account and region
- View ECS Clusters, Services, and Tasks
- Three tabs: Clusters, Services, Tasks
- Detailed information with graphs and charts
- CSV export per tab
- Corrected services counting logic

Uses your utils.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
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
st.set_page_config(page_title="ECS", page_icon="🐳", layout="wide")

# Initialize session state
if 'ecs_data' not in st.session_state:
    st.session_state.ecs_data = {
        'clusters': None,
        'services': None,
        'tasks': None
    }
if 'ecs_last_refresh' not in st.session_state:
    st.session_state.ecs_last_refresh = None
if 'ecs_errors' not in st.session_state:
    st.session_state.ecs_errors = []

st.title("🐳 ECS Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="ecs")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_ecs_client(account_id, role_name, region):
    """Get ECS client"""
    credentials = assume_role(account_id, role_name)
    if not credentials:
        return None
    
    return boto3.client(
        'ecs',
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_ecs_resources(account_id, account_name, region, role_name):
    """Get ECS resources"""
    resources = {
        'clusters': [],
        'services': [],
        'tasks': []
    }
    errors = []
    
    try:
        ecs = get_ecs_client(account_id, role_name, region)
        if not ecs:
            errors.append(f"❌ {account_name}/{region}: Failed to get ECS client")
            return resources, errors
        
        # ==================== CLUSTERS ====================
        try:
            clusters_resp = ecs.list_clusters()
            
            for cluster_arn in clusters_resp.get('clusterArns', []):
                cluster_detail = ecs.describe_clusters(clusters=[cluster_arn])
                
                for cluster in cluster_detail['clusters']:
                    # Get running and pending count from tasks in this cluster
                    tasks_resp = ecs.list_tasks(cluster=cluster_arn)
                    running_count = 0
                    pending_count = 0
                    
                    if tasks_resp.get('taskArns'):
                        # Paginate tasks if needed
                        all_task_arns = tasks_resp['taskArns']
                        for i in range(0, len(all_task_arns), 100):
                            batch = all_task_arns[i:i+100]
                            task_detail = ecs.describe_tasks(cluster=cluster_arn, tasks=batch)
                            for task in task_detail['tasks']:
                                if task['lastStatus'] == 'RUNNING':
                                    running_count += 1
                                elif task['lastStatus'] == 'PENDING':
                                    pending_count += 1
                    
                    resources['clusters'].append({
                        'Account Name': account_name,
                        'Account ID': account_id,
                        'Region': region,
                        'Cluster Name': cluster['clusterName'],
                        'Cluster ARN': cluster['clusterArn'],
                        'Status': cluster['status'],
                        'Running Tasks': running_count,
                        'Pending Tasks': pending_count,
                        'Active Services': cluster.get('activeServicesCount', 0),
                        'Registered Instances': cluster.get('registeredContainerInstancesCount', 0)
                    })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching Clusters - {str(e)}")
        
        # ==================== SERVICES ====================
        try:
            clusters_resp = ecs.list_clusters()
            
            for cluster_arn in clusters_resp.get('clusterArns', []):
                # Paginate through services
                paginator = ecs.get_paginator('list_services')
                page_iterator = paginator.paginate(cluster=cluster_arn)
                
                for page in page_iterator:
                    service_arns = page.get('serviceArns', [])
                    
                    if service_arns:
                        # Describe services in batches (max 10 per request)
                        for i in range(0, len(service_arns), 10):
                            batch = service_arns[i:i+10]
                            service_detail = ecs.describe_services(cluster=cluster_arn, services=batch)
                            
                            for service in service_detail['services']:
                                resources['services'].append({
                                    'Account Name': account_name,
                                    'Account ID': account_id,
                                    'Region': region,
                                    'Cluster Name': cluster_arn.split('/')[-1],
                                    'Service Name': service['serviceName'],
                                    'Service ARN': service['serviceArn'],
                                    'Status': service['status'],
                                    'Desired Count': service.get('desiredCount', 0),
                                    'Running Count': service.get('runningCount', 0),
                                    'Pending Count': service.get('pendingCount', 0),
                                    'Launch Type': service.get('launchType', 'N/A'),
                                    'Task Definition': service.get('taskDefinition', 'N/A').split('/')[-1]
                                })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching Services - {str(e)}")
        
        # ==================== TASKS ====================
        try:
            clusters_resp = ecs.list_clusters()
            
            for cluster_arn in clusters_resp.get('clusterArns', []):
                tasks_resp = ecs.list_tasks(cluster=cluster_arn)
                
                if tasks_resp.get('taskArns'):
                    # Paginate through tasks if there are many
                    all_task_arns = tasks_resp['taskArns']
                    
                    # Describe tasks in batches (max 100 per request)
                    for i in range(0, len(all_task_arns), 100):
                        batch = all_task_arns[i:i+100]
                        task_detail = ecs.describe_tasks(cluster=cluster_arn, tasks=batch)
                        
                        for task in task_detail['tasks']:
                            created_at = task.get('createdAt', 'N/A')
                            if created_at != 'N/A':
                                try:
                                    created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')
                                except:
                                    pass
                            
                            resources['tasks'].append({
                                'Account Name': account_name,
                                'Account ID': account_id,
                                'Region': region,
                                'Cluster Name': cluster_arn.split('/')[-1],
                                'Task ARN': task['taskArn'].split('/')[-1],
                                'Task Definition': task.get('taskDefinitionArn', 'N/A').split('/')[-1],
                                'Status': task['lastStatus'],
                                'Launch Type': task.get('launchType', 'N/A'),
                                'Created At': created_at,
                                'CPU': task.get('cpu', 'N/A'),
                                'Memory': task.get('memory', 'N/A')
                            })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching Tasks - {str(e)}")
        
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return resources, errors

def fetch_data(account_ids, all_accounts, regions, role_name):
    """Fetch ECS data with parallel processing"""
    all_resources = {
        'clusters': [],
        'services': [],
        'tasks': []
    }
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
                future = executor.submit(get_ecs_resources, account_id, account_name, region, role_name)
                futures[future] = (account_id, account_name, region)
        
        for future in as_completed(futures):
            account_id, account_name, region = futures[future]
            completed += 1
            status_text.text(f"📡 {account_name}/{region} ({completed}/{total})")
            progress_bar.progress(completed / total)
            
            try:
                resources, errors = future.result()
                for key in all_resources:
                    all_resources[key].extend(resources[key])
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"❌ {account_name}/{region}: Failed - {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return all_resources, all_errors

# ============================================================================
# FETCH BUTTON
# ============================================================================

if st.session_state.get('ecs_fetch_clicked', False):
    if not account_ids or not regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.ecs_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Fetching ECS resources..."):
            resources, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
            st.session_state.ecs_data = resources
            st.session_state.ecs_errors = errors
            st.session_state.ecs_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        ecs_count = sum(len(v) for v in resources.values() if v)
        if ecs_count > 0:
            st.success(f"✅ ECS resources fetched in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No ECS resources in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.ecs_fetch_clicked = False

# ============================================================================
# DISPLAY WITH TABS
# ============================================================================

if debug_mode and st.session_state.ecs_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.ecs_errors:
            st.write(error)

if st.session_state.ecs_data['clusters'] is not None:
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.ecs_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.ecs_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                resources, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
                st.session_state.ecs_data = resources
                st.session_state.ecs_errors = errors
                st.session_state.ecs_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = time.time() - start_time
            st.success(f"✅ Refreshed in {elapsed:.2f}s")
            if errors:
                with st.expander(f"⚠️ Messages ({len(errors)})"):
                    for error in errors:
                        st.write(error)
            st.rerun()
    
    st.markdown("---")
    
    # ==================== FILTERS ====================
    st.subheader("🔍 Filters")
    
    col1, col2 = st.columns(2)
    
    all_accounts_list = set()
    all_regions_list = set()
    
    for resources in st.session_state.ecs_data.values():
        for item in (resources if resources else []):
            if 'Account Name' in item:
                all_accounts_list.add(item['Account Name'])
            if 'Region' in item:
                all_regions_list.add(item['Region'])
    
    with col1:
        account_filter = st.multiselect(
            "Account:",
            options=sorted(all_accounts_list),
            default=sorted(all_accounts_list),
            key="ecs_account_filter"
        )
    
    with col2:
        region_filter = st.multiselect(
            "Region:",
            options=sorted(all_regions_list),
            default=sorted(all_regions_list),
            key="ecs_region_filter"
        )
    
    st.markdown("---")
    
    # Helper function to filter data
    def apply_filters(data, account_filter, region_filter):
        df = pd.DataFrame(data)
        if df.empty:
            return df
        
        df = df[df['Account Name'].isin(account_filter)]
        df = df[df['Region'].isin(region_filter)]
        
        return df
    
    # ==================== TABS ====================
    tab1, tab2, tab3 = st.tabs(["🎯 Clusters", "⚙️ Services", "📦 Tasks"])
    
    # TAB 1: CLUSTERS
    with tab1:
        st.subheader("ECS Clusters")
        df_clusters = apply_filters(st.session_state.ecs_data['clusters'], account_filter, region_filter)
        
        if df_clusters.empty:
            st.info("No Clusters found.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Clusters", len(df_clusters))
            with col2:
                total_running = int(df_clusters['Running Tasks'].sum())
                st.metric("Total Running Tasks", total_running)
            with col3:
                total_pending = int(df_clusters['Pending Tasks'].sum())
                st.metric("Total Pending Tasks", total_pending)
            with col4:
                total_services = int(df_clusters['Active Services'].sum())
                st.metric("Total Active Services", total_services)
            
            st.markdown("---")
            
            # Charts for Clusters
            graph_col1, graph_col2 = st.columns(2)
            
            with graph_col1:
                # Clusters by Account
                cluster_by_account = df_clusters['Account Name'].value_counts()
                fig_account = px.bar(
                    x=cluster_by_account.index,
                    y=cluster_by_account.values,
                    title="Clusters by Account",
                    labels={'x': 'Account', 'y': 'Count'}
                )
                fig_account.update_traces(marker_color='#2ca02c')
                st.plotly_chart(fig_account, use_container_width=True)
            
            with graph_col2:
                # Clusters by Region
                cluster_by_region = df_clusters['Region'].value_counts()
                fig_region = px.bar(
                    x=cluster_by_region.index,
                    y=cluster_by_region.values,
                    title="Clusters by Region",
                    labels={'x': 'Region', 'y': 'Count'}
                )
                fig_region.update_traces(marker_color='#ff7f0e')
                st.plotly_chart(fig_region, use_container_width=True)
            
            # Task Status Distribution
            task_status_data = []
            for _, row in df_clusters.iterrows():
                task_status_data.append({'Cluster': row['Cluster Name'], 'Running': row['Running Tasks'], 'Pending': row['Pending Tasks']})
            
            if task_status_data:
                df_task_status = pd.DataFrame(task_status_data)
                fig_task_status = px.bar(
                    df_task_status,
                    x='Cluster',
                    y=['Running', 'Pending'],
                    title="Task Status by Cluster",
                    barmode='group',
                    labels={'value': 'Count', 'variable': 'Status'}
                )
                st.plotly_chart(fig_task_status, use_container_width=True)
            
            st.markdown("---")
            st.dataframe(df_clusters, use_container_width=True, hide_index=True)
            
            csv = df_clusters.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"ecs_clusters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # TAB 2: SERVICES
    with tab2:
        st.subheader("ECS Services")
        df_services = apply_filters(st.session_state.ecs_data['services'], account_filter, region_filter)
        
        if df_services.empty:
            st.info("No Services found.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Services", len(df_services))
            with col2:
                total_desired = int(df_services['Desired Count'].sum())
                st.metric("Total Desired", total_desired)
            with col3:
                total_running = int(df_services['Running Count'].sum())
                st.metric("Total Running", total_running)
            with col4:
                total_pending = int(df_services['Pending Count'].sum())
                st.metric("Total Pending", total_pending)
            
            st.markdown("---")
            
            # Charts for Services
            graph_col1, graph_col2 = st.columns(2)
            
            with graph_col1:
                # Launch Type Distribution
                launch_type = df_services['Launch Type'].value_counts()
                fig_launch = px.pie(
                    values=launch_type.values,
                    names=launch_type.index,
                    title="Services by Launch Type",
                    hole=0.3
                )
                st.plotly_chart(fig_launch, use_container_width=True)
            
            with graph_col2:
                # Services by Status
                status_count = df_services['Status'].value_counts()
                fig_status = px.pie(
                    values=status_count.values,
                    names=status_count.index,
                    title="Services by Status",
                    hole=0.3
                )
                st.plotly_chart(fig_status, use_container_width=True)
            
            # Service Task Counts
            service_counts = df_services[['Service Name', 'Desired Count', 'Running Count', 'Pending Count']].head(20)
            if not service_counts.empty:
                fig_service_counts = px.bar(
                    service_counts,
                    x='Service Name',
                    y=['Desired Count', 'Running Count', 'Pending Count'],
                    title="Top 20 Services - Task Counts",
                    barmode='group',
                    labels={'value': 'Count', 'variable': 'Type'}
                )
                fig_service_counts.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_service_counts, use_container_width=True)
            
            st.markdown("---")
            st.dataframe(df_services, use_container_width=True, hide_index=True)
            
            csv = df_services.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"ecs_services_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # TAB 3: TASKS
    with tab3:
        st.subheader("ECS Tasks")
        df_tasks = apply_filters(st.session_state.ecs_data['tasks'], account_filter, region_filter)
        
        if df_tasks.empty:
            st.info("No Tasks found.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Tasks", len(df_tasks))
            with col2:
                running_tasks = len(df_tasks[df_tasks['Status'] == 'RUNNING'])
                st.metric("Running", running_tasks)
            with col3:
                pending_tasks = len(df_tasks[df_tasks['Status'] == 'PENDING'])
                st.metric("Pending", pending_tasks)
            
            st.markdown("---")
            
            # Charts for Tasks
            graph_col1, graph_col2 = st.columns(2)
            
            with graph_col1:
                # Task Status Distribution
                status_counts = df_tasks['Status'].value_counts()
                fig_task_status = px.pie(
                    values=status_counts.values,
                    names=status_counts.index,
                    title="Task Status Distribution",
                    hole=0.3
                )
                st.plotly_chart(fig_task_status, use_container_width=True)
            
            with graph_col2:
                # Launch Type Distribution
                launch_type = df_tasks['Launch Type'].value_counts()
                fig_launch = px.pie(
                    values=launch_type.values,
                    names=launch_type.index,
                    title="Tasks by Launch Type",
                    hole=0.3
                )
                st.plotly_chart(fig_launch, use_container_width=True)
            
            # Tasks by Cluster
            tasks_by_cluster = df_tasks['Cluster Name'].value_counts()
            fig_cluster = px.bar(
                x=tasks_by_cluster.index,
                y=tasks_by_cluster.values,
                title="Tasks by Cluster",
                labels={'x': 'Cluster', 'y': 'Count'}
            )
            fig_cluster.update_traces(marker_color='#1f77b4')
            st.plotly_chart(fig_cluster, use_container_width=True)
            
            st.markdown("---")
            st.dataframe(df_tasks, use_container_width=True, hide_index=True)
            
            csv = df_tasks.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"ecs_tasks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
