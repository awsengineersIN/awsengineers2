"""
Updated utils.py with Organization Hierarchy Support

Fetches AWS Organizations structure with OUs and displays in hierarchical format
"""

import streamlit as st
import boto3
from botocore.exceptions import ClientError

@st.cache_data(ttl=3600)
def get_organization_hierarchy():
    """Fetch complete organization hierarchy with OUs and accounts"""
    try:
        org_client = boto3.client("organizations")
        
        # Get root
        roots = org_client.list_roots()['Roots']
        if not roots:
            return None
        
        root = roots[0]
        hierarchy = {
            'Id': root['Id'],
            'Name': root['Name'],
            'Type': 'ROOT',
            'Arn': root['Arn'],
            'Children': [],
            'Accounts': []
        }
        
        def build_hierarchy(parent_id, parent_node):
            """Recursively build hierarchy of OUs and accounts"""
            
            # Get child OUs
            try:
                paginator = org_client.get_paginator('list_organizational_units_for_parent')
                for page in paginator.paginate(ParentId=parent_id):
                    for ou in page['OrganizationalUnits']:
                        ou_node = {
                            'Id': ou['Id'],
                            'Name': ou['Name'],
                            'Type': 'OU',
                            'Arn': ou['Arn'],
                            'Children': [],
                            'Accounts': []
                        }
                        parent_node['Children'].append(ou_node)
                        # Recursively process this OU
                        build_hierarchy(ou['Id'], ou_node)
            except:
                pass
            
            # Get accounts in this parent
            try:
                paginator = org_client.get_paginator('list_accounts_for_parent')
                for page in paginator.paginate(ParentId=parent_id):
                    for account in page['Accounts']:
                        if account['Status'] == 'ACTIVE':
                            account_node = {
                                'Id': account['Id'],
                                'Name': account['Name'],
                                'Email': account['Email'],
                                'Status': account['Status'],
                                'Type': 'ACCOUNT',
                                'Arn': account['Arn']
                            }
                            parent_node['Accounts'].append(account_node)
            except:
                pass
        
        # Build the hierarchy
        build_hierarchy(root['Id'], hierarchy)
        
        return hierarchy
        
    except Exception as e:
        st.error(f"Failed to fetch organization hierarchy: {str(e)}")
        return None

@st.cache_data(ttl=3600)
def get_organization_accounts():
    """Fetch all accounts from AWS Organizations (flat list)"""
    session = boto3.Session()
    org_client = session.client("organizations", verify=False)
    accounts = []
    paginator = org_client.get_paginator("list_accounts")
    for page in paginator.paginate():
        for account in page["Accounts"]:
            if account["Status"] == "ACTIVE":
                accounts.append({
                    "Id": account["Id"],
                    "Name": account["Name"],
                    "Email": account["Email"],
                    "Status": account["Status"],
                })
    return accounts

def assume_role(
    account_id,
    role_name="readonly-role",
    session_name="dashboard-session",
):
    """Assume role in specified account and return credentials"""
    try:
        sts = boto3.client("sts")
        response = sts.assume_role(
            RoleArn=f"arn:aws:iam::{account_id}:role/{role_name}",
            RoleSessionName=session_name,
        )
        return response["Credentials"]
    except Exception as e:
        st.error(f"Failed to assume role in account {account_id}: {str(e)}")
        return None

def setup_account_filter(page_key=""):
    st.sidebar.header("⚙️ Configuration")
    accounts = st.session_state.get("accounts", [])
    if not accounts:
        st.sidebar.error("No accounts loaded")
        return [], []

    accounts = sorted(accounts, key=lambda x: x["Name"])

    st.sidebar.subheader("👥 Accounts")
    account_names = [f"{acc['Name']} ({acc['Id']})" for acc in accounts]
    account_ids = [acc["Id"] for acc in accounts]

    select_all_key = f"{page_key}_select_all_accounts"
    if select_all_key not in st.session_state:
        st.session_state[select_all_key] = True

    select_all = st.sidebar.checkbox(
        "Select All Accounts",
        value=st.session_state[select_all_key],
        key=f"{page_key}_select_all_cb",
    )

    st.session_state[select_all_key] = select_all

    if select_all:
        st.sidebar.info("✅ All accounts selected")
        selected_account_id = account_ids
    else:
        selected_names = st.sidebar.multiselect(
            "Choose accounts:",
            options=account_names,
            default=[],
            key=f"{page_key}_accounts"
        )
        selected_account_id = [
            account_ids[account_names.index(name)] for name in selected_names
        ]

    st.sidebar.subheader("🌍 Regions")
    region_mode = st.sidebar.radio(
        "Region mode:", ["Common", "All"],
        key=f"{page_key}_region_mode"
    )

    if region_mode == "Common":
        selected_regions = st.sidebar.multiselect(
            "Select regions:",
            options=DEFAULT_REGIONS,
            default=DEFAULT_REGIONS,
            key=f"{page_key}_regions",
        )
    elif region_mode == "All":
        all_regions = get_all_regions()
        selected_regions = st.sidebar.multiselect(
            "Select regions:",
            options=all_regions,
            default=DEFAULT_REGIONS,
            key=f"{page_key}_regions_all",
        )

    st.sidebar.markdown("---")

    if st.sidebar.button(
        "Fetch Data",
        type="primary",
        use_container_width=True,
        key=f"{page_key}_fetch"
    ):
        st.session_state[f"{page_key}_fetch_clicked"] = True
        st.rerun()

    return selected_account_id, selected_regions

def get_account_name_by_id(account_id, accounts_list):
    for account in accounts_list:
        if account["Id"] == account_id:
            return account["Name"]
    return account_id

DEFAULT_REGIONS = [
    "us-east-1",
    "us-west-2",
]

@st.cache_data
def get_all_regions():
    import boto3
    try:
        ec2 = boto3.client("ec2", region_name="us-east-1")
        response = ec2.describe_regions(AllRegions=False)
        return sorted([r["RegionName"] for r in response["Regions"]])
    except:
        return DEFAULT_REGIONS
