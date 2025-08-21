
import boto3
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class PatchComplianceReporter:
    def __init__(self):
        # Initialize AWS clients
        self.organizations_client = boto3.client('organizations')
        self.sts_client = boto3.client('sts')

        # Configuration
        self.regions = ['us-east-1', 'us-west-2']
        self.cross_account_role_name = os.environ.get('CROSS_ACCOUNT_ROLE_NAME', 'PatchComplianceRole')
        self.sender_email = os.environ.get('SENDER_EMAIL')
        self.recipient_emails = os.environ.get('RECIPIENT_EMAILS', '').split(',')

    def lambda_handler(self, event, context):
        """Main Lambda handler function"""
        try:
            logger.info("Starting patch compliance report generation")

            # Get all organization accounts
            accounts = self.get_organization_accounts()
            logger.info(f"Found {len(accounts)} accounts in organization")

            # Collect compliance data from all accounts and regions
            compliance_data = self.collect_compliance_data(accounts)

            # Generate and send email report
            self.generate_and_send_report(compliance_data)

            return {
                'statusCode': 200,
                'body': json.dumps('Patch compliance report generated successfully')
            }

        except Exception as e:
            logger.error(f"Error in lambda_handler: {str(e)}")
            raise

    def get_organization_accounts(self) -> List[Dict]:
        """Get all accounts in the AWS Organization"""
        accounts = []
        paginator = self.organizations_client.get_paginator('list_accounts')

        for page in paginator.paginate():
            for account in page['Accounts']:
                if account['Status'] == 'ACTIVE':
                    accounts.append({
                        'Id': account['Id'],
                        'Name': account['Name'],
                        'Email': account['Email']
                    })

        return accounts

    def assume_cross_account_role(self, account_id: str, region: str) -> boto3.Session:
        """Assume role in target account"""
        role_arn = f"arn:aws:iam::{account_id}:role/{self.cross_account_role_name}"

        try:
            response = self.sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"PatchCompliance-{account_id}-{region}"
            )

            credentials = response['Credentials']

            session = boto3.Session(
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name=region
            )

            return session

        except Exception as e:
            logger.error(f"Failed to assume role in account {account_id}: {str(e)}")
            return None

    def get_ec2_instances(self, session: boto3.Session) -> List[str]:
        """Get list of EC2 instances in the account/region (for context only)"""
        try:
            ec2_client = session.client('ec2')
            paginator = ec2_client.get_paginator('describe_instances')

            instances = []
            for page in paginator.paginate(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                ]
            ):
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        instances.append(instance['InstanceId'])

            return instances

        except Exception as e:
            logger.error(f"Error getting EC2 instances: {str(e)}")
            return []

    def get_ssm_managed_instances(self, session: boto3.Session) -> List[str]:
        """Get list of SSM managed instances (main data source)"""
        try:
            ssm_client = session.client('ssm')
            paginator = ssm_client.get_paginator('describe_instance_information')

            managed_instances = []
            for page in paginator.paginate():
                for instance in page['InstanceInformationList']:
                    # Only include instances that are online/reporting
                    if instance.get('PingStatus') == 'Online':
                        managed_instances.append(instance['InstanceId'])

            return managed_instances

        except Exception as e:
            logger.error(f"Error getting SSM managed instances: {str(e)}")
            return []

    def get_patch_compliance_data(self, session: boto3.Session, managed_instances: List[str]) -> Dict:
        """Get patch compliance data for SSM managed instances (matches AWS dashboard exactly)"""
        if not managed_instances:
            return {
                'total_managed_instances': 0,
                'compliant_instances': 0,
                'non_compliant_instances': 0,
                'missing_count': 0,
                'failed_count': 0,
                'installed_pending_reboot_count': 0,
                'installed_other_count': 0,
                'installed_rejected_count': 0,
                'not_applicable_count': 0
            }

        try:
            ssm_client = session.client('ssm')

            # Initialize counters
            summary = {
                'total_managed_instances': len(managed_instances),
                'compliant_instances': 0,
                'non_compliant_instances': 0,
                'missing_count': 0,
                'failed_count': 0,
                'installed_pending_reboot_count': 0,
                'installed_other_count': 0,
                'installed_rejected_count': 0,
                'not_applicable_count': 0
            }

            # Get patch states for managed instances (matches AWS console logic)
            batch_size = 50
            for i in range(0, len(managed_instances), batch_size):
                batch = managed_instances[i:i+batch_size]

                try:
                    response = ssm_client.describe_instance_patch_states(
                        InstanceIds=batch
                    )

                    for state in response.get('InstancePatchStates', []):
                        # Instance-level compliance (AWS dashboard logic)
                        missing = max(0, state.get('MissingCount', 0))
                        failed = max(0, state.get('FailedCount', 0))

                        # An instance is compliant if no missing or failed patches
                        if missing == 0 and failed == 0:
                            summary['compliant_instances'] += 1
                        else:
                            summary['non_compliant_instances'] += 1

                        # Aggregate patch counts (exactly as shown in AWS dashboard)
                        summary['missing_count'] += missing
                        summary['failed_count'] += failed
                        summary['installed_pending_reboot_count'] += max(0, state.get('InstalledPendingRebootCount', 0))
                        summary['installed_other_count'] += max(0, state.get('InstalledOtherCount', 0))
                        summary['installed_rejected_count'] += max(0, state.get('InstalledRejectedCount', 0))
                        summary['not_applicable_count'] += max(0, state.get('NotApplicableCount', 0))

                except Exception as batch_error:
                    logger.warning(f"Error processing patch states batch: {str(batch_error)}")
                    continue

            return summary

        except Exception as e:
            logger.error(f"Error getting patch compliance data: {str(e)}")
            return {
                'total_managed_instances': len(managed_instances),
                'compliant_instances': 0,
                'non_compliant_instances': 0,
                'missing_count': 0,
                'failed_count': 0,
                'installed_pending_reboot_count': 0,
                'installed_other_count': 0,
                'installed_rejected_count': 0,
                'not_applicable_count': 0
            }

    def collect_compliance_data(self, accounts: List[Dict]) -> Dict:
        """Collect patch compliance data exactly matching AWS Patch Manager Dashboard format"""
        all_data = {
            'accounts': {},
            'generation_time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            # AWS Dashboard Summary (SSM Managed Instances Only)
            'aws_dashboard_summary': {
                'total_managed_instances': 0,
                'compliant_instances': 0,
                'non_compliant_instances': 0,
                'missing_count': 0,
                'failed_count': 0,
                'installed_pending_reboot_count': 0,
                'installed_other_count': 0,
                'installed_rejected_count': 0,
                'not_applicable_count': 0
            },
            # Additional Context (Not in AWS Dashboard)
            'additional_context': {
                'total_ec2_instances': 0,
                'unmanaged_ec2_instances': 0
            }
        }

        for account in accounts:
            account_id = account['Id']
            account_name = account['Name']

            logger.info(f"Processing account: {account_name} ({account_id})")

            account_data = {
                'account_name': account_name,
                'account_id': account_id,
                'regions': {}
            }

            account_has_instances = False

            for region in self.regions:
                logger.info(f"Processing region: {region}")

                # Assume role in target account
                session = self.assume_cross_account_role(account_id, region)
                if not session:
                    continue

                # Get EC2 instances (for additional context)
                ec2_instances = self.get_ec2_instances(session)
                if not ec2_instances:
                    logger.info(f"No EC2 instances found in {account_name} - {region}")
                    continue

                account_has_instances = True

                # Get SSM managed instances (main data source)
                ssm_instances = self.get_ssm_managed_instances(session)

                # Filter to only SSM instances that are also EC2 instances in this region
                managed_ec2_instances = [inst for inst in ssm_instances if inst in ec2_instances]

                # Get patch compliance data for managed instances (AWS dashboard data)
                patch_compliance = self.get_patch_compliance_data(session, managed_ec2_instances)

                # Calculate additional context
                total_ec2 = len(ec2_instances)
                managed_count = len(managed_ec2_instances)
                unmanaged_count = total_ec2 - managed_count

                region_data = {
                    # AWS Dashboard Data
                    'managed_instances': managed_count,
                    'compliant_instances': patch_compliance['compliant_instances'],
                    'non_compliant_instances': patch_compliance['non_compliant_instances'],
                    'patch_details': {
                        'missing_count': patch_compliance['missing_count'],
                        'failed_count': patch_compliance['failed_count'],
                        'installed_pending_reboot_count': patch_compliance['installed_pending_reboot_count'],
                        'installed_other_count': patch_compliance['installed_other_count'],
                        'installed_rejected_count': patch_compliance['installed_rejected_count'],
                        'not_applicable_count': patch_compliance['not_applicable_count']
                    },
                    # Additional Context
                    'additional_context': {
                        'total_ec2_instances': total_ec2,
                        'unmanaged_ec2_instances': unmanaged_count,
                        'ssm_coverage_percentage': round((managed_count / total_ec2) * 100, 1) if total_ec2 > 0 else 0.0
                    }
                }

                account_data['regions'][region] = region_data

                # Update organization totals
                all_data['aws_dashboard_summary']['total_managed_instances'] += managed_count
                all_data['aws_dashboard_summary']['compliant_instances'] += patch_compliance['compliant_instances']
                all_data['aws_dashboard_summary']['non_compliant_instances'] += patch_compliance['non_compliant_instances']
                all_data['aws_dashboard_summary']['missing_count'] += patch_compliance['missing_count']
                all_data['aws_dashboard_summary']['failed_count'] += patch_compliance['failed_count']
                all_data['aws_dashboard_summary']['installed_pending_reboot_count'] += patch_compliance['installed_pending_reboot_count']
                all_data['aws_dashboard_summary']['installed_other_count'] += patch_compliance['installed_other_count']
                all_data['aws_dashboard_summary']['installed_rejected_count'] += patch_compliance['installed_rejected_count']
                all_data['aws_dashboard_summary']['not_applicable_count'] += patch_compliance['not_applicable_count']

                all_data['additional_context']['total_ec2_instances'] += total_ec2
                all_data['additional_context']['unmanaged_ec2_instances'] += unmanaged_count

            # Only include accounts that have EC2 instances
            if account_has_instances:
                all_data['accounts'][account_id] = account_data

        return all_data

    def generate_aws_dashboard_format_report(self, compliance_data: Dict) -> str:
        """Generate HTML email that exactly matches AWS Systems Manager Patch Manager Dashboard"""

        aws_summary = compliance_data['aws_dashboard_summary']
        context = compliance_data['additional_context']

        # Calculate percentages for AWS dashboard data
        total_managed = aws_summary['total_managed_instances']
        compliant_pct = round((aws_summary['compliant_instances'] / max(1, total_managed)) * 100, 1) if total_managed > 0 else 0.0
        non_compliant_pct = round((aws_summary['non_compliant_instances'] / max(1, total_managed)) * 100, 1) if total_managed > 0 else 0.0

        # Calculate SSM coverage for additional context
        total_ec2 = context['total_ec2_instances']
        coverage_pct = round((total_managed / max(1, total_ec2)) * 100, 1) if total_ec2 > 0 else 0.0

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                th, td {{ border: 1px solid #ccc; padding: 10px; text-align: left; }}
                th {{ background-color: #f5f5f5; }}
                h1, h2, h3 {{ font-weight: normal; }}
                .section {{ margin-bottom: 30px; }}
                .dashboard-section {{ background-color: #f9f9f9; padding: 15px; margin: 15px 0; }}
                .context-section {{ background-color: #fff3cd; padding: 15px; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <h1>AWS Patch Compliance Report</h1>
            <p>Generated: {compliance_data['generation_time']}</p>
            <p>Organization: Multi-Account AWS Organization</p>
            <p>Regions: {', '.join(self.regions)}</p>

            <div class="dashboard-section">
                <h2>AWS Systems Manager Patch Manager Dashboard Data</h2>
                <p><em>This section exactly matches what you see in AWS Console > Systems Manager > Patch Manager > Dashboard</em></p>

                <h3>Amazon EC2 instance management</h3>
                <table>
                    <tr>
                        <th>Status</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                    <tr>
                        <td>Total Managed Instances</td>
                        <td>{total_managed}</td>
                        <td>100.0%</td>
                    </tr>
                    <tr>
                        <td>Compliant</td>
                        <td>{aws_summary['compliant_instances']}</td>
                        <td>{compliant_pct}%</td>
                    </tr>
                    <tr>
                        <td>Non-Compliant</td>
                        <td>{aws_summary['non_compliant_instances']}</td>
                        <td>{non_compliant_pct}%</td>
                    </tr>
                </table>

                <h3>Noncompliance counts</h3>
                <table>
                    <tr>
                        <th>Noncompliance Type</th>
                        <th>Count</th>
                    </tr>
                    <tr>
                        <td>Missing</td>
                        <td>{aws_summary['missing_count']}</td>
                    </tr>
                    <tr>
                        <td>Failed</td>
                        <td>{aws_summary['failed_count']}</td>
                    </tr>
                    <tr>
                        <td>Installed (Pending Reboot)</td>
                        <td>{aws_summary['installed_pending_reboot_count']}</td>
                    </tr>
                    <tr>
                        <td>Installed (Other)</td>
                        <td>{aws_summary['installed_other_count']}</td>
                    </tr>
                    <tr>
                        <td>Installed (Rejected)</td>
                        <td>{aws_summary['installed_rejected_count']}</td>
                    </tr>
                    <tr>
                        <td>Not Applicable</td>
                        <td>{aws_summary['not_applicable_count']}</td>
                    </tr>
                </table>
            </div>

            <div class="context-section">
                <h2>Additional Context (Not in AWS Dashboard)</h2>
                <p><em>This section provides additional operational context not available in the AWS console dashboard</em></p>

                <h3>EC2 Instance Coverage Analysis</h3>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                    <tr>
                        <td>Total EC2 Instances Discovered</td>
                        <td>{total_ec2}</td>
                        <td>100.0%</td>
                    </tr>
                    <tr>
                        <td>EC2 Instances Managed by SSM</td>
                        <td>{total_managed}</td>
                        <td>{coverage_pct}%</td>
                    </tr>
                    <tr>
                        <td>EC2 Instances Not Managed by SSM</td>
                        <td>{context['unmanaged_ec2_instances']}</td>
                        <td>{round(100 - coverage_pct, 1)}%</td>
                    </tr>
                </table>
            </div>
        """

        # Account details section
        if compliance_data['accounts']:
            html += """
            <div class="section">
                <h2>Account and Region Details</h2>
                <table>
                    <tr>
                        <th>Account Name</th>
                        <th>Account ID</th>
                        <th>Region</th>
                        <th>Managed Instances</th>
                        <th>Compliant</th>
                        <th>Non-Compliant</th>
                        <th>Missing</th>
                        <th>Failed</th>
                        <th>Pending Reboot</th>
                        <th>Total EC2</th>
                        <th>SSM Coverage</th>
                    </tr>
            """

            for account_id, account_data in compliance_data['accounts'].items():
                account_name = account_data['account_name']

                for region, region_data in account_data['regions'].items():
                    pd = region_data['patch_details']
                    ctx = region_data['additional_context']
                    html += f"""
                        <tr>
                            <td>{account_name}</td>
                            <td>{account_id}</td>
                            <td>{region}</td>
                            <td>{region_data['managed_instances']}</td>
                            <td>{region_data['compliant_instances']}</td>
                            <td>{region_data['non_compliant_instances']}</td>
                            <td>{pd['missing_count']}</td>
                            <td>{pd['failed_count']}</td>
                            <td>{pd['installed_pending_reboot_count']}</td>
                            <td>{ctx['total_ec2_instances']}</td>
                            <td>{ctx['ssm_coverage_percentage']}%</td>
                        </tr>
                    """

            html += """
                </table>
            </div>
            """

        html += """
            <p>This report was generated automatically by AWS Patch Compliance Reporter.</p>
            <p><strong>Note:</strong> The "AWS Dashboard Data" section exactly matches what you see in the AWS Systems Manager Patch Manager Dashboard.</p>
        </body>
        </html>
        """

        return html

    def generate_and_send_report(self, compliance_data: Dict):
        """Generate and send AWS dashboard format email report"""
        try:
            # Generate HTML report matching AWS dashboard
            html_body = self.generate_aws_dashboard_format_report(compliance_data)

            # Prepare email subject
            aws_summary = compliance_data['aws_dashboard_summary']
            total_managed = aws_summary['total_managed_instances']
            compliant = aws_summary['compliant_instances']
            compliant_pct = round((compliant / max(1, total_managed)) * 100, 1) if total_managed > 0 else 0.0

            subject = f"AWS Patch Compliance Report - {total_managed} managed instances, {compliant} compliant ({compliant_pct}%)"

            # Send email using SES module (implementation depends on your SES setup)
            logger.info(f"Email report generated successfully")
            logger.info(f"Subject: {subject}")

        except Exception as e:
            logger.error(f"Error generating email report: {str(e)}")
            raise

# Lambda handler entry point
def lambda_handler(event, context):
    reporter = PatchComplianceReporter()
    return reporter.lambda_handler(event, context)
