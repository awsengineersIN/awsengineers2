"""
SSM Patch Compliance Dashboard - Complete Rewrite

Features:
- Multi-account, multi-region patch compliance monitoring
- Real-time instance patch status tracking
- Compliance metrics and visualizations
- Patch group management overview
- Available patches and severity analysis
- CSV export capabilities
- Managed vs Unmanaged instance tracking

Built for 40+ AWS accounts with parallel processing
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import boto3
import plotly.graph_objects as go

from utils import assume_role, setup_account_filter, get_account_name_by_id

# ============================================================================
# PAGE CONFIG & STATE
# ============================================================================

st.set_page_config(page_title="Patch Compliance", page_icon="🔧", layout="wide")

if 'pc_data' not in st.session_state:
    st.session_state.pc_data = None
if 'pc_refresh_time' not in st.session_state:
    st.session_state.pc_refresh_time = None

st.title("🔧 SSM Patch Compliance Dashboard")

# ============================================================================
# AWS CLIENTS
# ============================================================================

def get_ssm(account_id, role, region):
    """Get SSM client for account"""
    try:
        creds = assume_role(account_id, role)
        if not creds:
            return None
        return boto3.client('ssm', region_name=region, 
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'])
    except:
        return None

def get_ec2(account_id, role, region):
    """Get EC2 client for account"""
    try:
        creds = assume_role(account_id, role)
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

def fetch_account_region_data(account_id, account_name, region, role):
    """Fetch patch compliance for single account/region"""
    instances = []
    groups = []
    patches = []
    errors = []
    
    ssm = get_ssm(account_id, role, region)
    ec2 = get_ec2(account_id, role, region)
    
    if not ssm or not ec2:
        errors.append(f"❌ {account_name}/{region}: Auth failed")
        return instances, groups, patches, errors
    
    # Get all EC2 instances
    instance_map = {}
    try:
        paginator = ec2.get_paginator('describe_instances')
        for page in paginator.paginate(Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]):
            for res in page.get('Reservations', []):
                for inst in res.get('Instances', []):
                    iid = inst['InstanceId']
                    instance_map[iid] = {
                        'name': next((t['Value'] for t in inst.get('Tags', []) if t['Key'] == 'Name'), iid),
                        'platform': inst.get('Platform', 'windows') or 'linux',
                        'state': inst['State']['Name'],
                        'launch': inst['LaunchTime'].strftime('%Y-%m-%d') if 'LaunchTime' in inst else 'N/A',
                        'managed': False
                    }
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: EC2 error - {str(e)[:50]}")
    
    # Get managed instances
    managed_ids = set()
    try:
        paginator = ssm.get_paginator('describe_instance_information')
        for page in paginator.paginate():
            for inst in page.get('InstanceInformationList', []):
                iid = inst['InstanceId']
                managed_ids.add(iid)
                if iid in instance_map:
                    instance_map[iid]['managed'] = True
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: SSM instances - {str(e)[:50]}")
    
    # Get patch states
    try:
        paginator = ssm.get_paginator('describe_instance_patch_states')
        for page in paginator.paginate():
            for state in page.get('InstancePatchStates', []):
                iid = state['InstanceId']
                if iid not in instance_map:
                    continue
                
                installed = state.get('InstalledCount', 0)
                missing = state.get('MissingCount', 0)
                failed = state.get('FailedCount', 0)
                
                if failed > 0:
                    status = 'FAILED'
                elif missing > 0:
                    status = 'MISSING'
                else:
                    status = 'COMPLIANT'
                
                instances.append({
                    'Account': account_name,
                    'Region': region,
                    'Instance ID': iid,
                    'Name': instance_map[iid]['name'],
                    'Platform': instance_map[iid]['platform'],
                    'Status': status,
                    'Installed': installed,
                    'Missing': missing,
                    'Failed': failed,
                    'State': instance_map[iid]['state'],
                    'Launch': instance_map[iid]['launch'],
                    'Managed': True
                })
                instance_map[iid]['managed'] = True
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: Patch states - {str(e)[:50]}")
    
    # Add unmanaged instances
    for iid, info in instance_map.items():
        if not info['managed']:
            instances.append({
                'Account': account_name,
                'Region': region,
                'Instance ID': iid,
                'Name': info['name'],
                'Platform': info['platform'],
                'Status': 'UNMANAGED',
                'Installed': 0,
                'Missing': 0,
                'Failed': 0,
                'State': info['state'],
                'Launch': info['launch'],
                'Managed': False
            })
    
    # Get patch groups (only if we have instances)
    try:
        paginator = ssm.get_paginator('describe_patch_groups')
        for page in paginator.paginate():
            for group in page.get('Mappings', []):
                group_name = group.get('PatchGroup', 'N/A')
                baseline_id = group.get('BaselineIdentity', {}).get('BaselineId', 'N/A')
                
                try:
                    resp = ssm.describe_patch_group_state(PatchGroup=group_name)
                    count = resp.get('Instances', 0)
                    if count > 0:
                        groups.append({
                            'Account': account_name,
                            'Region': region,
                            'Group': group_name,
                            'Baseline': baseline_id,
                            'Total': count,
                            'Compliant': resp.get('InstancesWithInstalledPatches', 0),
                            'Failed': resp.get('InstancesWithFailedPatches', 0),
                            'Other': resp.get('InstancesWithUnreportedNotApplicablePatches', 0)
                        })
                except:
                    pass
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: Patch groups - {str(e)[:50]}")
    
    # Get available patches
    try:
        paginator = ssm.get_paginator('describe_available_patches')
        for page in paginator.paginate():
            for patch in page.get('Patches', []):
                patches.append({
                    'Account': account_name,
                    'Region': region,
                    'ID': patch.get('Id', 'N/A'),
                    'Title': patch.get('Title', 'N/A'),
                    'Classification': patch.get('Classification', 'N/A'),
                    'Severity': patch.get('Severity', 'N/A'),
                    'Released': str(patch.get('ReleaseDate', 'N/A'))
                })
    except Exception as e:
        errors.append(f"⚠️ {account_name}/{region}: Patches - {str(e)[:50]}")
    
    return instances, groups, patches, errors

def fetch_all_data(account_ids, accounts, regions):
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
            aname = get_account_name_by_id(aid, accounts)
            for rgn in regions:
                f = exe.submit(fetch_account_region_data, aid, aname, rgn, "readonly-role")
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
# SIDEBAR & CONTROLS
# ============================================================================

account_ids, regions = setup_account_filter(page_key="pc")

st.sidebar.markdown("---")
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("📊 Fetch", type="primary", use_container_width=True):
        if not account_ids or not regions:
            st.error("Select accounts & regions")
        else:
            with st.spinner("Scanning..."):
                start = time.time()
                inst, grp, pat, err = fetch_all_data(account_ids, st.session_state.get('accounts', []), regions)
                st.session_state.pc_data = {'inst': inst, 'grp': grp, 'pat': pat, 'err': err}
                st.session_state.pc_refresh_time = datetime.now()
            elapsed = time.time() - start
            st.success(f"✅ Done in {elapsed:.1f}s")
            if err:
                with st.expander(f"⚠️ {len(err)} messages"):
                    for e in err:
                        st.text(e)

with col2:
    if st.button("🔁 Refresh", use_container_width=True) and st.session_state.pc_data:
        with st.spinner("Refreshing..."):
            start = time.time()
            inst, grp, pat, err = fetch_all_data(account_ids, st.session_state.get('accounts', []), regions)
            st.session_state.pc_data = {'inst': inst, 'grp': grp, 'pat': pat, 'err': err}
            st.session_state.pc_refresh_time = datetime.now()
        elapsed = time.time() - start
        st.success(f"✅ Refreshed in {elapsed:.1f}s")
        st.rerun()

# ============================================================================
# DISPLAY
# ============================================================================

if not st.session_state.pc_data:
    st.info("👈 Select accounts/regions, then click Fetch")
else:
    data = st.session_state.pc_data
    inst_df = pd.DataFrame(data['inst']) if data['inst'] else pd.DataFrame()
    grp_df = pd.DataFrame(data['grp']) if data['grp'] else pd.DataFrame()
    pat_df = pd.DataFrame(data['pat']) if data['pat'] else pd.DataFrame()
    
    if inst_df.empty and grp_df.empty and pat_df.empty:
        st.warning("No data found")
    else:
        # Refresh time
        if st.session_state.pc_refresh_time:
            st.caption(f"Last updated: {st.session_state.pc_refresh_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        st.markdown("---")
        
        # ===== METRICS =====
        st.subheader("📊 Summary")
        
        comp = len(inst_df[inst_df['Status'] == 'COMPLIANT']) if not inst_df.empty else 0
        miss = len(inst_df[inst_df['Status'] == 'MISSING']) if not inst_df.empty else 0
        fail = len(inst_df[inst_df['Status'] == 'FAILED']) if not inst_df.empty else 0
        unmg = len(inst_df[inst_df['Status'] == 'UNMANAGED']) if not inst_df.empty else 0
        total = len(inst_df)
        mngd = total - unmg
        
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("🟢 Compliant", comp)
        with m2:
            st.metric("🟡 Missing", miss)
        with m3:
            st.metric("🔴 Failed", fail)
        with m4:
            st.metric("⚫ Unmanaged", unmg)
        with m5:
            if total > 0:
                pct = (comp / total) * 100
                st.metric("Total", total)
        
        st.markdown("---")
        
        # ===== FILTERS =====
        st.subheader("🔍 Filters")
        f1, f2, f3 = st.columns(3)
        
        with f1:
            acc_opts = sorted(inst_df['Account'].unique()) if not inst_df.empty else []
            acc_sel = st.multiselect("Account:", acc_opts, default=acc_opts, key="pc_acc")
        
        with f2:
            rgn_opts = sorted(inst_df['Region'].unique()) if not inst_df.empty else []
            rgn_sel = st.multiselect("Region:", rgn_opts, default=rgn_opts, key="pc_rgn")
        
        with f3:
            sts_opts = sorted(inst_df['Status'].unique()) if not inst_df.empty else []
            sts_sel = st.multiselect("Status:", sts_opts, default=sts_opts, key="pc_sts")
        
        filtered = inst_df[(inst_df['Account'].isin(acc_sel)) & 
                           (inst_df['Region'].isin(rgn_sel)) & 
                           (inst_df['Status'].isin(sts_sel))] if not inst_df.empty else pd.DataFrame()
        
        st.markdown("---")
        
        # ===== CHARTS =====
        st.subheader("📈 Visualizations")
        
        c1, c2, c3 = st.columns(3)
        
        # Managed vs Unmanaged
        with c1:
            mng_data = [mngd, unmg]
            mng_labs = ['Managed', 'Unmanaged']
            mng_cols = ['#28a745', '#dc3545']
            fig = go.Figure(data=[go.Pie(labels=mng_labs, values=mng_data, marker=dict(colors=mng_cols), hole=0.3)])
            fig.update_layout(title_text="Management Status", height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        # Compliance
        with c2:
            comp_data = [comp, miss, fail, unmg]
            comp_labs = ['Compliant', 'Missing Patches', 'Failed Patches', 'Unmanaged']
            comp_cols = ['#28a745', '#fd7e14', '#dc3545', '#6c757d']
            comp_data_flt = [v for v, l in zip(comp_data, comp_labs) if v > 0]
            comp_labs_flt = [l for v, l in zip(comp_data, comp_labs) if v > 0]
            comp_cols_flt = [c for v, c in zip(comp_data, comp_cols) if v > 0]
            fig = go.Figure(data=[go.Pie(labels=comp_labs_flt, values=comp_data_flt, marker=dict(colors=comp_cols_flt), hole=0.3)])
            fig.update_layout(title_text="Compliance Summary", height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        # Non-compliance reasons
        with c3:
            if not filtered.empty:
                miss_cnt = len(filtered[filtered['Missing'] > 0])
                fail_cnt = len(filtered[filtered['Failed'] > 0])
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
                    fig.update_layout(title_text="Non-Compliance Reasons", height=400)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No non-compliance")
            else:
                st.info("No data")
        
        st.markdown("---")
        
        # ===== TABS =====
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Patch Groups", "🖥️ Instances", "📦 Patches", "📊 Severity"])
        
        with tab1:
            st.subheader("Patch Groups")
            if not grp_df.empty:
                show_df = grp_df[['Account', 'Region', 'Group', 'Baseline', 'Total', 'Compliant', 'Failed', 'Other']]
                st.dataframe(show_df, use_container_width=True, hide_index=True, height=500)
                csv = show_df.to_csv(index=False)
                st.download_button("📥 CSV", csv, f"groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
            else:
                st.info("No data")
        
        with tab2:
            st.subheader("Instances")
            if not filtered.empty:
                show_df = filtered[['Instance ID', 'Name', 'Account', 'Region', 'Platform', 'Status', 'Installed', 'Missing', 'Failed', 'State']]
                
                def style_status(row):
                    colors = {
                        'COMPLIANT': '#d4edda',
                        'MISSING': '#fff3cd',
                        'FAILED': '#f8d7da',
                        'UNMANAGED': '#e2e3e5'
                    }
                    color = colors.get(row['Status'], '#ffffff')
                    return ['background-color:' + color] * len(row)
                
                st.dataframe(show_df.style.apply(style_status, axis=1), use_container_width=True, hide_index=True, height=500)
                csv = show_df.to_csv(index=False)
                st.download_button("📥 CSV", csv, f"instances_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
            else:
                st.info("No data")
        
        with tab3:
            st.subheader("Available Patches")
            if not pat_df.empty:
                uniq = pat_df.drop_duplicates(subset=['ID'])
                show_df = uniq[['ID', 'Title', 'Classification', 'Severity']].sort_values('Severity', ascending=False)
                
                def style_sev(row):
                    colors = {
                        'Critical': '#dc3545',
                        'High': '#fd7e14',
                        'Medium': '#ffc107',
                        'Low': '#d4edda'
                    }
                    color = colors.get(row['Severity'], '#ffffff')
                    return ['background-color:' + color] * len(row)
                
                st.dataframe(show_df.style.apply(style_sev, axis=1), use_container_width=True, hide_index=True, height=500)
                csv = show_df.to_csv(index=False)
                st.download_button("📥 CSV", csv, f"patches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
            else:
                st.info("No data")
        
        with tab4:
            st.subheader("Severity Analysis")
            if not pat_df.empty:
                sev_counts = pat_df['Severity'].value_counts()
                cls_counts = pat_df['Classification'].value_counts()
                
                c1, c2 = st.columns(2)
                
                with c1:
                    fig = go.Figure(data=[go.Pie(labels=sev_counts.index, values=sev_counts.values, hole=0.3)])
                    fig.update_layout(title_text="By Severity", height=400)
                    st.plotly_chart(fig, use_container_width=True)
                
                with c2:
                    fig = go.Figure(data=[go.Bar(x=cls_counts.index, y=cls_counts.values, marker_color='#1f77b4')])
                    fig.update_layout(title_text="By Classification", height=400, xaxis_title="Classification", yaxis_title="Count")
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No data")
