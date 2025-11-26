"""
VPC Dashboard

Features:
- Filter by account, region, and VPC ID
- Six tabs: VPCs, Subnets, NACLs, Route Tables, IGWs, NAT Gateways
- Detailed tabular information for each tab

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

# Page configuration
st.set_page_config(page_title="VPC", page_icon="🌐", layout="wide")

# Initialize session state
if 'vpc_data' not in st.session_state:
    st.session_state.vpc_data = {
        'vpcs': None,
        'subnets': None,
        'nacls': None,
        'route_tables': None,
        'igws': None,
        'nat_gateways': None
    }
if 'vpc_last_refresh' not in st.session_state:
    st.session_state.vpc_last_refresh = None
if 'vpc_errors' not in st.session_state:
    st.session_state.vpc_errors = []

st.title("🌐 VPC Dashboard")

# Get accounts
all_accounts = st.session_state.get('accounts', [])
if not all_accounts:
    st.error("No accounts found. Please return to main page.")
    st.stop()

# Sidebar
account_ids, regions = setup_account_filter(page_key="vpc")

st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("Show Debug Info", value=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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

def get_vpc_resources(account_id, account_name, region, role_name):
    """Get all VPC resources"""
    resources = {
        'vpcs': [],
        'subnets': [],
        'nacls': [],
        'route_tables': [],
        'igws': [],
        'nat_gateways': []
    }
    errors = []
    
    try:
        ec2 = get_ec2_client(account_id, role_name, region)
        if not ec2:
            errors.append(f"❌ {account_name}/{region}: Failed to get EC2 client")
            return resources, errors
        
        # ==================== VPCs ====================
        try:
            vpcs_resp = ec2.describe_vpcs()
            for vpc in vpcs_resp['Vpcs']:
                resources['vpcs'].append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'VPC ID': vpc['VpcId'],
                    'CIDR Block': vpc['CidrBlock'],
                    'State': vpc['State'],
                    'Is Default': vpc['IsDefault'],
                    'DHCP Options Set': vpc['DhcpOptionsId'],
                    'Tags': str(vpc.get('Tags', []))
                })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching VPCs - {str(e)}")
        
        # ==================== SUBNETS ====================
        try:
            subnets_resp = ec2.describe_subnets()
            for subnet in subnets_resp['Subnets']:
                resources['subnets'].append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'Subnet ID': subnet['SubnetId'],
                    'VPC ID': subnet['VpcId'],
                    'CIDR Block': subnet['CidrBlock'],
                    'Availability Zone': subnet['AvailabilityZone'],
                    'Available IPs': subnet['AvailableIpAddressCount'],
                    'State': subnet['State'],
                    'Map Public IP on Launch': subnet['MapPublicIpOnLaunch'],
                    'Tags': str(subnet.get('Tags', []))
                })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching Subnets - {str(e)}")
        
        # ==================== NACLs ====================
        try:
            nacls_resp = ec2.describe_network_acls()
            for nacl in nacls_resp['NetworkAcls']:
                resources['nacls'].append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'NACL ID': nacl['NetworkAclId'],
                    'VPC ID': nacl['VpcId'],
                    'Is Default': nacl['IsDefault'],
                    'Entry Count': len(nacl['Entries']),
                    'Associated Subnets': len(nacl['Associations']),
                    'Tags': str(nacl.get('Tags', []))
                })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching NACLs - {str(e)}")
        
        # ==================== ROUTE TABLES ====================
        try:
            rt_resp = ec2.describe_route_tables()
            for rt in rt_resp['RouteTables']:
                resources['route_tables'].append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'Route Table ID': rt['RouteTableId'],
                    'VPC ID': rt['VpcId'],
                    'Route Count': len(rt['Routes']),
                    'Associated Subnets': len(rt['Associations']),
                    'Owner ID': rt['OwnerId'],
                    'Tags': str(rt.get('Tags', []))
                })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching Route Tables - {str(e)}")
        
        # ==================== INTERNET GATEWAYS ====================
        try:
            igws_resp = ec2.describe_internet_gateways()
            for igw in igws_resp['InternetGateways']:
                attached_vpc = "None"
                if igw['Attachments']:
                    attached_vpc = igw['Attachments'][0]['VpcId']
                
                resources['igws'].append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'IGW ID': igw['InternetGatewayId'],
                    'Attached VPC': attached_vpc,
                    'State': igw['Attachments'][0]['State'] if igw['Attachments'] else 'Detached',
                    'Owner ID': igw['OwnerId'],
                    'Tags': str(igw.get('Tags', []))
                })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching IGWs - {str(e)}")
        
        # ==================== NAT GATEWAYS ====================
        try:
            nat_resp = ec2.describe_nat_gateways()
            for nat in nat_resp['NatGateways']:
                resources['nat_gateways'].append({
                    'Account ID': account_id,
                    'Account Name': account_name,
                    'Region': region,
                    'NAT Gateway ID': nat['NatGatewayId'],
                    'Subnet ID': nat['SubnetId'],
                    'VPC ID': nat['VpcId'],
                    'State': nat['State'],
                    'Public IP': nat.get('PublicIp', 'N/A'),
                    'Private IP': nat.get('PrivateIp', 'N/A'),
                    'Elastic IP ID': nat.get('AllocationId', 'N/A'),
                    'Tags': str(nat.get('Tags', []))
                })
        except Exception as e:
            errors.append(f"⚠️ {account_name}/{region}: Error fetching NAT Gateways - {str(e)}")
        
    except Exception as e:
        errors.append(f"❌ {account_name}/{region}: Unexpected error - {str(e)}")
    
    return resources, errors

def fetch_data(account_ids, all_accounts, regions, role_name):
    """Fetch VPC data with parallel processing"""
    all_resources = {
        'vpcs': [],
        'subnets': [],
        'nacls': [],
        'route_tables': [],
        'igws': [],
        'nat_gateways': []
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
                future = executor.submit(get_vpc_resources, account_id, account_name, region, role_name)
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

if st.session_state.get('vpc_fetch_clicked', False):
    if not account_ids or not regions:
        st.warning("⚠️ Please select at least one account and region.")
        st.session_state.vpc_fetch_clicked = False
    else:
        start_time = time.time()
        
        with st.spinner(f"🔍 Fetching VPC resources..."):
            resources, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
            st.session_state.vpc_data = resources
            st.session_state.vpc_errors = errors
            st.session_state.vpc_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        elapsed = time.time() - start_time
        
        vpc_count = sum(len(v) for v in resources.values())
        if vpc_count > 0:
            st.success(f"✅ VPC resources fetched in {elapsed:.2f}s")
        else:
            st.warning(f"⚠️ No VPC resources in {elapsed:.2f}s")
        
        if errors:
            with st.expander(f"⚠️ Messages ({len(errors)})", expanded=True):
                for error in errors:
                    st.write(error)
        
        st.session_state.vpc_fetch_clicked = False

# ============================================================================
# DISPLAY WITH TABS
# ============================================================================

if debug_mode and st.session_state.vpc_errors:
    with st.expander("🐛 Debug Info"):
        for error in st.session_state.vpc_errors:
            st.write(error)

if st.session_state.vpc_data['vpcs'] is not None:
    # Refresh button
    col1, col2 = st.columns([5, 1])
    with col1:
        if st.session_state.vpc_last_refresh:
            st.caption(f"Last refreshed: {st.session_state.vpc_last_refresh}")
    with col2:
        if st.button("🔁 Refresh", type="secondary", use_container_width=True):
            start_time = time.time()
            with st.spinner("🔍 Refreshing..."):
                resources, errors = fetch_data(account_ids, all_accounts, regions, "readonly-role")
                st.session_state.vpc_data = resources
                st.session_state.vpc_errors = errors
                st.session_state.vpc_last_refresh = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
    
    col1, col2, col3 = st.columns(3)
    
    # Collect all unique values
    all_vpc_ids = set()
    all_accounts_list = set()
    all_regions_list = set()
    
    for resources in st.session_state.vpc_data.values():
        for item in resources:
            if 'VPC ID' in item:
                all_vpc_ids.add(item['VPC ID'])
            if 'Account Name' in item:
                all_accounts_list.add(item['Account Name'])
            if 'Region' in item:
                all_regions_list.add(item['Region'])
    
    with col1:
        account_filter = st.multiselect(
            "Account:",
            options=sorted(all_accounts_list),
            default=sorted(all_accounts_list),
            key="vpc_account_filter"
        )
    
    with col2:
        region_filter = st.multiselect(
            "Region:",
            options=sorted(all_regions_list),
            default=sorted(all_regions_list),
            key="vpc_region_filter"
        )
    
    with col3:
        vpc_filter = st.multiselect(
            "VPC ID:",
            options=sorted(all_vpc_ids),
            default=sorted(all_vpc_ids),
            key="vpc_vpc_filter"
        )
    
    st.markdown("---")
    
    # Helper function to filter data
    def apply_filters(data, account_filter, region_filter, vpc_filter):
        df = pd.DataFrame(data)
        if df.empty:
            return df
        
        df = df[df['Account Name'].isin(account_filter)]
        df = df[df['Region'].isin(region_filter)]
        
        if 'VPC ID' in df.columns:
            df = df[df['VPC ID'].isin(vpc_filter)]
        
        return df
    
    # ==================== TABS ====================
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🌐 VPCs", "🔗 Subnets", "🛡️ NACLs", "🚦 Route Tables", "🚪 IGWs", "🔌 NAT Gateways"])
    
    # TAB 1: VPCs
    with tab1:
        st.subheader("Virtual Private Clouds")
        df_vpcs = apply_filters(st.session_state.vpc_data['vpcs'], account_filter, region_filter, vpc_filter)
        
        if df_vpcs.empty:
            st.info("No VPCs found.")
        else:
            st.metric("Total VPCs", len(df_vpcs))
            st.dataframe(df_vpcs, use_container_width=True, hide_index=True)
            
            csv = df_vpcs.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"vpcs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # TAB 2: SUBNETS
    with tab2:
        st.subheader("Subnets")
        df_subnets = apply_filters(st.session_state.vpc_data['subnets'], account_filter, region_filter, vpc_filter)
        
        if df_subnets.empty:
            st.info("No Subnets found.")
        else:
            st.metric("Total Subnets", len(df_subnets))
            st.dataframe(df_subnets, use_container_width=True, hide_index=True)
            
            csv = df_subnets.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"subnets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # TAB 3: NACLs
    with tab3:
        st.subheader("Network Access Control Lists")
        df_nacls = apply_filters(st.session_state.vpc_data['nacls'], account_filter, region_filter, vpc_filter)
        
        if df_nacls.empty:
            st.info("No NACLs found.")
        else:
            st.metric("Total NACLs", len(df_nacls))
            st.dataframe(df_nacls, use_container_width=True, hide_index=True)
            
            csv = df_nacls.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"nacls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # TAB 4: ROUTE TABLES
    with tab4:
        st.subheader("Route Tables")
        df_rts = apply_filters(st.session_state.vpc_data['route_tables'], account_filter, region_filter, vpc_filter)
        
        if df_rts.empty:
            st.info("No Route Tables found.")
        else:
            st.metric("Total Route Tables", len(df_rts))
            st.dataframe(df_rts, use_container_width=True, hide_index=True)
            
            csv = df_rts.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"route_tables_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # TAB 5: IGWs
    with tab5:
        st.subheader("Internet Gateways")
        df_igws = apply_filters(st.session_state.vpc_data['igws'], account_filter, region_filter, vpc_filter)
        
        if df_igws.empty:
            st.info("No Internet Gateways found.")
        else:
            st.metric("Total IGWs", len(df_igws))
            st.dataframe(df_igws, use_container_width=True, hide_index=True)
            
            csv = df_igws.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"igws_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    
    # TAB 6: NAT GATEWAYS
    with tab6:
        st.subheader("NAT Gateways")
        df_nats = apply_filters(st.session_state.vpc_data['nat_gateways'], account_filter, region_filter, vpc_filter)
        
        if df_nats.empty:
            st.info("No NAT Gateways found.")
        else:
            st.metric("Total NAT Gateways", len(df_nats))
            st.dataframe(df_nats, use_container_width=True, hide_index=True)
            
            csv = df_nats.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"nat_gateways_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")

else:
    st.info("👈 Select accounts and regions, then click 'Fetch Data'")
