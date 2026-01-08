"""
SSM Patch Compliance Dashboard - FIXED VERSION

Features:
- Filter by account and region
- View patch compliance status across instances
- Patch compliance summary with aggregated statistics
- Detailed patch compliance report by instance
- Patch details with severity breakdown
- Tabs: Instances, Patch Groups Summary, Available Patches, Missing Patches
- Color-coded compliance status (RED for Non-Compliant, GREEN for Compliant)
- Metrics: Compliant, Non-Compliant, Missing patches
- Visualizations: Managed instances, Compliance summary, Noncompliance reasons
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
import plotly.graph_objects as go
import plotly.express as px

from utils import assume_role, setup_account_filter, get_account_name_by_id

# ============================================================================
# PAGE CONFIG & STATE
# ============================================================================

st.set_page_config(page_title="Patch Compliance", page_icon="🔧", layout="wide")

if 'pc_data' not in st.session_state:
    st.session_state.pc_data = None
if 'pc_refresh_time' not in st.session_state:
    st.session_state.pc_refresh_time = None
if 'pc_fetch_clicked' not in st.session_state:
    st.session_state.pc_fetch_clicked = False

st.title("🔧 SSM Patch Compliance Dashboard")

# ============================================================================
# AWS CLIENTS
# ============================================================================

def get_ssm(account_id, role_name, region):
    """Get SSM client for account"""
    try:
        creds = assume_role(account_id, role_name)
        if not creds:
            return None
        return boto3.client('ssm', region_name=region, 
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'])
    except:
        return None

def get_ec2(account_id, role_name, region):
    """Get EC2 client for account"""
    try:
        creds = assume_role(account_id, role_name)
        if not creds:
            return None
        return boto3.client('ec2', region_name=region,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'])
    except:
        return None

# ============================================================================
# DATA COLLECTION
# ============================================================================

def fetch_account_region_data(account_id, account_name, region, role_name):
    """Fetch patch compliance for single account/region"""
    instances = []
    groups = []
    patches = []
    errors = []
    
    ssm = get_ssm(account_id, role_name, region)
    ec2 = get_ec2(account_id, role_name, region)
    
    if not ssm or not ec2:
        errors.append(f"❌ {account_name}/{region}: Auth failed")
        return instances, groups, patches, errors
    
    # Get all EC2 instances
    instance_map = {}
    try:
        paginator = ec2.get_paginator('describe_instances')
        for page in paginator.paginate():
            for res in page.get('Reservations', []):
                for inst in res.get('Instances', []):
                    iid = inst['InstanceId']
                    platform = inst.get('Platform', 'linux')
                    instance_map[iid] = {
                        'name': next((t['Value'] for t in inst.get('Tags', []) if t['Key'] == 'Name'), iid),
                        'platform': platform,
                        'state': inst['State']['Name'],
                        'launch': inst.get('LaunchTime', None),
                        'ssm_managed': False,
                        'ssm_agent_status': 'Unknown'
                    }
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: EC2 error - {str(e)[:50]}")
    
    # Get SSM agent status and managed instances
    try:
        paginator = ssm.get_paginator('describe_instance_information')
        for page in paginator.paginate():
            for inst in page.get('InstanceInformationList', []):
                iid = inst['InstanceId']
                if iid in instance_map:
                    instance_map[iid]['ssm_managed'] = True
                    instance_map[iid]['ssm_agent_status'] = inst.get('PingStatus', 'Unknown')
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: SSM instances - {str(e)[:50]}")
    
    # Get compliance summaries using list_resource_compliance_summaries
    try:
        paginator = ssm.get_paginator('list_resource_compliance_summaries')
        for page in paginator.paginate(Filters=[{'Key': 'ComplianceType', 'Values': ['PATCH']}]):
            for summary in page.get('ResourceComplianceSummaryItems', []):
                iid = summary.get('ResourceId', '')
                if iid not in instance_map:
                    continue
                
                status = summary.get('Status', 'NON_COMPLIANT')
                
                instances.append({
                    'Account Name': account_name,
                    'Region': region,
                    'Instance ID': iid,
                    'Instance Name': instance_map[iid]['name'],
                    'Platform': instance_map[iid]['platform'],
                    'Compliance Status': status,
                    'SSM Agent Status': instance_map[iid]['ssm_agent_status'],
                    'Instance State': instance_map[iid]['state'],
                    'Launch Time': instance_map[iid]['launch'],
                    'Managed': instance_map[iid]['ssm_managed']
                })
                instance_map[iid]['processed'] = True
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: Compliance summaries - {str(e)[:50]}")
    
    # Get detailed patch states for processed instances
    try:
        for iid in list(instance_map.keys()):
            if instance_map[iid].get('processed'):
                try:
                    patch_state = ssm.describe_instance_patch_states(InstanceIds=[iid])
                    if patch_state.get('InstancePatchStates'):
                        state = patch_state['InstancePatchStates'][0]
                        
                        # Find the corresponding instance and add patch details
                        for inst in instances:
                            if inst['Instance ID'] == iid:
                                inst['Installed Patches'] = state.get('InstalledCount', 0)
                                inst['Missing Patches'] = state.get('MissingCount', 0)
                                inst['Failed Patches'] = state.get('FailedCount', 0)
                                inst['Unspecified Patches'] = state.get('NotApplicableCount', 0) + state.get('UnreportedNotApplicableCount', 0)
                                break
                except:
                    pass
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: Patch details - {str(e)[:50]}")
    
    # Add unmanaged instances
    for iid, info in instance_map.items():
        if not info.get('processed') and not info.get('ssm_managed'):
            instances.append({
                'Account Name': account_name,
                'Region': region,
                'Instance ID': iid,
                'Instance Name': info['name'],
                'Platform': info['platform'],
                'Compliance Status': 'UNMANAGED',
                'SSM Agent Status': 'Not Installed',
                'Installed Patches': 0,
                'Missing Patches': 0,
                'Failed Patches': 0,
                'Unspecified Patches': 0,
                'Instance State': info['state'],
                'Launch Time': info['launch'],
                'Managed': False
            })
    
    # Get patch groups - NO FILTERING, collect all data
    try:
        paginator = ssm.get_paginator('describe_patch_groups')
        for page in paginator.paginate():
            for group in page.get('Mappings', []):
                group_name = group.get('PatchGroup', 'N/A')
                baseline_id = group.get('BaselineIdentity', {}).get('BaselineId', 'N/A')
                
                try:
                    resp = ssm.describe_patch_group_state(PatchGroup=group_name)
                    count = resp.get('Instances', 0)
                    compliant = resp.get('InstancesWithInstalledPatches', 0)
                    non_compliant = resp.get('InstancesWithMissingPatches', 0) + resp.get('InstancesWithFailedPatches', 0)
                    unspecified = resp.get('InstancesWithNotApplicablePatches', 0) + resp.get('InstancesWithUnreportedNotApplicablePatches', 0)
                    
                    # Collect all groups regardless of counts
                    if count > 0:
                        groups.append({
                            'Account Name': account_name,
                            'Region': region,
                            'Patch Group': group_name,
                            'Baseline ID': baseline_id,
                            'Instances Count': count,
                            'Compliant': compliant,
                            'Non-Compliant': non_compliant,
                            'Unspecified': unspecified
                        })
                except Exception as ge:
                    pass
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: Patch groups - {str(e)[:50]}")
    
    # Get available patches
    try:
        paginator = ssm.get_paginator('describe_available_patches')
        for page in paginator.paginate():
            for patch in page.get('Patches', []):
                patches.append({
                    'Account Name': account_name,
                    'Region': region,
                    'Patch ID': patch.get('Id', 'N/A'),
                    'Title': patch.get('Title', 'N/A'),
                    'Classification': patch.get('Classification', 'N/A'),
                    'Severity': patch.get('Severity', 'N/A'),
                    'Release Date': patch.get('ReleaseDate', None),
                    'Content URL': patch.get('ContentUrl', 'N/A')
                })
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: Patches - {str(e)[:50]}")
    
    return instances, groups, patches, errors

def fetch_all_data(account_ids, all_accounts, regions, role_name):
    """Fetch from all accounts/regions in parallel"""
    all_inst = []
    all_grp = []
    all_pat = []
    all_err = []
    
    progress = st.progress(0)
    status = st.empty()
    total = len(account_ids) * len(regions)
    done = 0
    
    with ThreadPoolExecutor(max_workers=10) as exe:
        futures = {}
        for aid in account_ids:
            aname = get_account_name_by_id(aid, all_accounts)
            for rgn in regions:
                f = exe.submit(fetch_account_region_data, aid, aname, rgn, role_name)
                futures[f] = (aname, rgn)
        
        for f in as_completed(futures):
            aname, rgn = futures[f]
            done += 1
            status.text(f"📡 {aname}/{rgn} ({done}/{total})")
            progress.progress(done / total)
            
            try:
                i, g, p, e = f.result()
                all_inst.extend(i)
                all_grp.extend(g)
                all_pat.extend(p)
                all_err.extend(e)
            except Exception as ex:
                all_err.append(f"❌ {aname}/{rgn}: {str(ex)[:50]}")
    
    progress.empty()
    status.empty()
    
    return all_inst, all_grp, all_pat, all_err

# ============================================================================
# SIDEBAR - ONLY ACCOUNT/REGION FILTERS, NO BUTTONS
# ============================================================================

all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

account_ids, regions = setup_account_filter(page_key="patch")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ONLY ONE BUTTON - in the sidebar
st.sidebar.markdown("---")
if st.sidebar.button("📊 Fetch Data", type="primary", use_container_width=True, key="fetch_patch_data"):
    st.session_state.pc_fetch_clicked = True

# ============================================================================
# FETCH DATA
# ============================================================================

if st.session_state.pc_fetch_clicked:
    if not account_ids or not regions:
        st.error("❌ Please select at least one account and region.")
        st.session_state.pc_fetch_clicked = False
    else:
        start = time.time()
        with st.spinner("🔍 Scanning patch compliance..."):
            inst, grp, pat, err = fetch_all_data(account_ids, all_accounts, regions, "readonly-role")
            st.session_state.pc_data = {'inst': inst, 'grp': grp, 'pat': pat, 'err': err}
            st.session_state.pc_refresh_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elapsed = time.time() - start
        st.success(f"✅ Patch compliance data fetched in {elapsed:.2f}s")
        if err:
            with st.expander(f"⚠️ Messages ({len(err)})", expanded=True):
                for e in err:
                    st.text(e)
        st.session_state.pc_fetch_clicked = False

# ============================================================================
# DISPLAY DASHBOARD
# ============================================================================

if debug_mode and st.session_state.pc_data and st.session_state.pc_data.get('err'):
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.pc_data['err']:
            st.write(error)

if not st.session_state.pc_data:
    st.info("👈 Select accounts and regions, then click 'Fetch Data' button in sidebar")
else:
    data = st.session_state.pc_data
    inst_df = pd.DataFrame(data['inst']) if data['inst'] else pd.DataFrame()
    grp_df = pd.DataFrame(data['grp']) if data['grp'] else pd.DataFrame()
    pat_df = pd.DataFrame(data['pat']) if data['pat'] else pd.DataFrame()
    
    if inst_df.empty and grp_df.empty and pat_df.empty:
        st.warning("⚠️ No patch compliance data found.")
    else:
        # Last refresh time
        if st.session_state.pc_refresh_time:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.caption(f"Last refreshed: {st.session_state.pc_refresh_time}")
            with col2:
                if st.button("🔁 Refresh", type="secondary", use_container_width=True):
                    start = time.time()
                    with st.spinner("🔍 Refreshing..."):
                        inst, grp, pat, err = fetch_all_data(account_ids, all_accounts, regions, "readonly-role")
                        st.session_state.pc_data = {'inst': inst, 'grp': grp, 'pat': pat, 'err': err}
                        st.session_state.pc_refresh_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    elapsed = time.time() - start
                    st.success(f"✅ Refreshed in {elapsed:.2f}s")
                    if err:
                        with st.expander(f"⚠️ Messages ({len(err)})"):
                            for e in err:
                                st.text(e)
                    st.rerun()
        
        st.markdown("---")
        
        # ===== METRICS =====
        st.subheader("📊 Summary")
        
        comp = len(inst_df[inst_df['Compliance Status'] == 'COMPLIANT']) if not inst_df.empty else 0
        non_comp = len(inst_df[inst_df['Compliance Status'] == 'NON_COMPLIANT']) if not inst_df.empty else 0
        unmg = len(inst_df[inst_df['Managed'] == False]) if not inst_df.empty else 0
        total = len(inst_df)
        total_missing = int(inst_df['Missing Patches'].sum()) if 'Missing Patches' in inst_df.columns and not inst_df.empty else 0
        total_failed = int(inst_df['Failed Patches'].sum()) if 'Failed Patches' in inst_df.columns and not inst_df.empty else 0
        
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("🟢 Compliant", comp)
        with m2:
            st.metric("🔴 Non-Compliant", non_comp)
        with m3:
            st.metric("📦 Missing Patches", total_missing)
        with m4:
            st.metric("Total Instances", total)
        with m5:
            if total > 0:
                pct = (comp / total) * 100
                st.metric("Compliance %", f"{pct:.1f}%")
        
        st.markdown("---")
        
        # ===== FILTERS =====
        st.subheader("🔍 Filters")
        f1, f2, f3 = st.columns(3)
        
        with f1:
            acc_opts = sorted(inst_df['Account Name'].unique()) if not inst_df.empty else []
            acc_sel = st.multiselect("Account:", acc_opts, default=acc_opts, key="patch_account")
        
        with f2:
            rgn_opts = sorted(inst_df['Region'].unique()) if not inst_df.empty else []
            rgn_sel = st.multiselect("Region:", rgn_opts, default=rgn_opts, key="patch_region")
        
        with f3:
            sts_opts = sorted(inst_df['Compliance Status'].unique()) if not inst_df.empty else []
            sts_sel = st.multiselect("Compliance Status:", sts_opts, default=sts_opts, key="patch_status")
        
        filtered = inst_df[(inst_df['Account Name'].isin(acc_sel)) & 
                           (inst_df['Region'].isin(rgn_sel)) & 
                           (inst_df['Compliance Status'].isin(sts_sel))] if not inst_df.empty else pd.DataFrame()
        
        st.markdown("---")
        
        # ===== CHARTS =====
        st.subheader("📈 Overview")
        
        c1, c2, c3 = st.columns(3)
        
        # Managed vs Unmanaged
        with c1:
            mng = total - unmg
            mng_data = [mng, unmg]
            mng_labs = ['Managed by SSM', 'Unmanaged']
            mng_cols = ['#28a745', '#dc3545']
            fig = go.Figure(data=[go.Pie(labels=mng_labs, values=mng_data, marker=dict(colors=mng_cols), hole=0.3)])
            fig.update_layout(title_text="Instance Management Status", height=400, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
        
        # Compliance Summary
        with c2:
            comp_data = [comp, non_comp, unmg]
            comp_labs = ['Compliant', 'Non-Compliant', 'Unmanaged']
            comp_cols = ['#28a745', '#dc3545', '#6c757d']
            comp_data_flt = [v for v, l in zip(comp_data, comp_labs) if v > 0]
            comp_labs_flt = [l for v, l in zip(comp_data, comp_labs) if v > 0]
            comp_cols_flt = [c for v, c in zip(comp_data, comp_cols) if v > 0]
            fig = go.Figure(data=[go.Pie(labels=comp_labs_flt, values=comp_data_flt, marker=dict(colors=comp_cols_flt), hole=0.3)])
            fig.update_layout(title_text="Compliance Summary", height=400, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
        
        # Non-compliance reasons
        with c3:
            if not filtered.empty and 'Missing Patches' in filtered.columns:
                miss_cnt = len(filtered[filtered['Missing Patches'] > 0])
                fail_cnt = len(filtered[filtered['Failed Patches'] > 0]) if 'Failed Patches' in filtered.columns else 0
                if miss_cnt > 0 or fail_cnt > 0:
                    nc_data = []
                    nc_labs = []
                    nc_cols = []
                    if miss_cnt > 0:
                        nc_data.append(miss_cnt)
                        nc_labs.append('Missing Patches')
                        nc_cols.append('#fd7e14')
                    if fail_cnt > 0:
                        nc_data.append(fail_cnt)
                        nc_labs.append('Failed Patches')
                        nc_cols.append('#dc3545')
                    fig = go.Figure(data=[go.Pie(labels=nc_labs, values=nc_data, marker=dict(colors=nc_cols), hole=0.3)])
                    fig.update_layout(title_text="Non-Compliance Reasons", height=400, showlegend=True)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("ℹ️ No non-compliance data")
            else:
                st.info("ℹ️ No data to display")
        
        st.markdown("---")
        
        # Additional charts
        if not filtered.empty:
            c1, c2 = st.columns(2)
            
            with c1:
                acc_counts = filtered['Account Name'].value_counts()
                fig = go.Figure(data=[go.Bar(x=acc_counts.index, y=acc_counts.values, marker_color='#ff7f0e')])
                fig.update_layout(title_text="Instances by Account", xaxis_title="Account", yaxis_title="Count", height=400)
                st.plotly_chart(fig, use_container_width=True)
            
            with c2:
                plt_counts = filtered['Platform'].value_counts()
                fig = go.Figure(data=[go.Bar(x=plt_counts.index, y=plt_counts.values, marker_color='#1f77b4')])
                fig.update_layout(title_text="Instances by Platform", xaxis_title="Platform", yaxis_title="Count", height=400)
                st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
        
        # ===== TABS =====
        tab1, tab2, tab3, tab4 = st.tabs(["🖥️ Instances", "📋 Patch Groups", "🔵 Available Patches", "📊 Missing Patches"])
        
        with tab1:
            st.subheader("Instance Patch Compliance Report")
            
            if not filtered.empty:
                display_cols = ['Instance ID', 'Instance Name', 'Platform', 'Compliance Status', 'SSM Agent Status', 'Managed', 'Instance State', 'Account Name', 'Region']
                if 'Missing Patches' in filtered.columns:
                    display_cols.insert(5, 'Missing Patches')
                display_df = filtered[display_cols].sort_values('Compliance Status').reset_index(drop=True)
                
                def highlight_compliance(row):
                    status = row['Compliance Status']
                    if status == 'NON_COMPLIANT':
                        return ['background-color: #f8d7da'] * len(row)
                    elif status == 'UNMANAGED':
                        return ['background-color: #e2e3e5'] * len(row)
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
        
        with tab2:
            st.subheader("Patch Groups Compliance Summary")
            
            if not grp_df.empty:
                display_cols = ['Patch Group', 'Baseline ID', 'Instances Count', 'Compliant', 'Non-Compliant', 'Unspecified', 'Account Name', 'Region']
                display_df = grp_df[display_cols].reset_index(drop=True)
                
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
        
        with tab3:
            st.subheader("Available Patches")
            
            if not pat_df.empty:
                unique_patches = pat_df.drop_duplicates(subset=['Patch ID']).copy()
                
                display_cols = ['Patch ID', 'Title', 'Classification', 'Severity', 'Release Date']
                display_df = unique_patches[display_cols].sort_values('Severity', ascending=False).reset_index(drop=True)
                
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
                    label="📥 Download Available Patches CSV",
                    data=csv,
                    file_name=f"available_patches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("ℹ️ No patch data available.")
        
        with tab4:
            st.subheader("Instances with Missing Patches")
            
            if not inst_df.empty and 'Missing Patches' in inst_df.columns:
                missing_patches_df = inst_df[inst_df['Missing Patches'] > 0].copy()
                
                if not missing_patches_df.empty:
                    display_cols = ['Instance ID', 'Instance Name', 'Account Name', 'Region', 'Missing Patches']
                    display_df = missing_patches_df[display_cols].sort_values('Missing Patches', ascending=False).reset_index(drop=True)
                    
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        height=500,
                        hide_index=True
                    )
                    
                    csv = display_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Missing Patches CSV",
                        data=csv,
                        file_name=f"missing_patches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.success("✅ All instances are fully patched!")
            else:
                st.info("ℹ️ No instance data available.")
