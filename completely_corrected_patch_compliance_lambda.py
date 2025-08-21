
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

    def get_instance_management_summary_from_explorer(self, session: boto3.Session) -> Dict:
        """Get EC2 instance management summary using GetOpsSummary API (same as Explorer dashboard uses)"""
        try:
            ssm_client = session.client('ssm')

            # Use GetOpsSummary API with AWS:EC2InstanceInformation TypeName (this is correct for Explorer)
            # This matches exactly what AWS Systems Manager Explorer dashboard uses
            response = ssm_client.get_ops_summary(
                Aggregators=[
                    {
                        'AggregatorType': 'Count',
                        'TypeName': 'AWS:EC2InstanceInformation',  # This is the correct TypeName
                        'AttributeName': 'PingStatus'  # Group by PingStatus to get managed vs not managed
                    }
                ],
                ResultAttributes=[
                    {
                        'TypeName': 'AWS:EC2InstanceInformation'
                    }
                ]
            )

            managed_count = 0  # Online instances
            not_managed_count = 0  # This needs to come from EC2 API since Explorer gets it from Config

            # Parse the response to extract managed instances (Online status)
            for entity in response.get('Entities', []):
                data = entity.get('Data', {})
                ec2_info_data = data.get('AWS:EC2InstanceInformation', {})
                content = ec2_info_data.get('Content', [])

                for item in content:
                    ping_status = item.get('PingStatus', '')
                    count = int(item.get('Count', 0))

                    if ping_status == 'Online':
                        managed_count += count

            # Get total EC2 instances from EC2 API (since Explorer gets this from Config)
            # This is necessary because GetOpsSummary only shows SSM managed instances
            total_ec2_instances = self.get_total_ec2_instances_from_ec2_api(session)
            not_managed_count = max(0, total_ec2_instances - managed_count)

            return {
                'total_ec2_instances': total_ec2_instances,
                'managed_instances': managed_count,
                'not_managed_instances': not_managed_count,
                'managed_percentage': round((managed_count / max(1, total_ec2_instances)) * 100, 1) if total_ec2_instances > 0 else 0.0
            }

        except Exception as e:
            logger.error(f"Error getting instance management summary from Explorer API: {str(e)}")
            # Fallback to traditional method if GetOpsSummary fails
            return self.get_instance_management_summary_fallback(session)

    def get_total_ec2_instances_from_ec2_api(self, session: boto3.Session) -> int:
        """Get total EC2 instances from EC2 API (to match what Config/Explorer sees)"""
        try:
            ec2_client = session.client('ec2')
            paginator = ec2_client.get_paginator('describe_instances')

            instance_count = 0
            for page in paginator.paginate(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                ]
            ):
                for reservation in page['Reservations']:
                    instance_count += len(reservation['Instances'])

            return instance_count

        except Exception as e:
            logger.error(f"Error getting total EC2 instances: {str(e)}")
            return 0

    def get_instance_management_summary_fallback(self, session: boto3.Session) -> Dict:
        """Fallback method using traditional APIs"""
        try:
            # Get all EC2 instances
            total_ec2_instances = self.get_total_ec2_instances_from_ec2_api(session)

            # Get SSM managed instances
            ssm_client = session.client('ssm')
            managed_count = 0

            try:
                paginator = ssm_client.get_paginator('describe_instance_information')
                for page in paginator.paginate():
                    for instance in page['InstanceInformationList']:
                        if instance.get('PingStatus') == 'Online':
                            managed_count += 1
            except Exception as ssm_error:
                logger.warning(f"Error getting SSM instances: {str(ssm_error)}")

            not_managed_count = max(0, total_ec2_instances - managed_count)

            return {
                'total_ec2_instances': total_ec2_instances,
                'managed_instances': managed_count,
                'not_managed_instances': not_managed_count,
                'managed_percentage': round((managed_count / max(1, total_ec2_instances)) * 100, 1) if total_ec2_instances > 0 else 0.0
            }

        except Exception as e:
            logger.error(f"Error in fallback instance management summary: {str(e)}")
            return {
                'total_ec2_instances': 0,
                'managed_instances': 0,
                'not_managed_instances': 0,
                'managed_percentage': 0.0
            }

    def get_patch_compliance_summary_from_compliance_api(self, session: boto3.Session) -> Dict:
        """Get patch compliance summary using ListComplianceSummaries API (same as Fleet Manager uses)"""
        try:
            ssm_client = session.client('ssm')

            # Use ListComplianceSummaries API exactly as Fleet Manager dashboard does
            response = ssm_client.list_compliance_summaries(
                Filters=[
                    {
                        'Key': 'ComplianceType',
                        'Values': ['Patch'],
                        'Type': 'EQUAL'
                    }
                ]
            )

            compliance_summary = {
                'compliant_instances': 0,
                'non_compliant_instances': 0,
                'critical_count': 0,
                'high_count': 0,
                'medium_count': 0,
                'low_count': 0,
                'informational_count': 0,
                'unspecified_count': 0
            }

            # Parse compliance summary items exactly as the console does
            for item in response.get('ComplianceSummaryItems', []):
                if item.get('ComplianceType') == 'Patch':
                    # Get compliant summary
                    compliant_summary = item.get('CompliantSummary', {})
                    compliance_summary['compliant_instances'] = compliant_summary.get('CompliantCount', 0)

                    # Get non-compliant summary  
                    non_compliant_summary = item.get('NonCompliantSummary', {})
                    compliance_summary['non_compliant_instances'] = non_compliant_summary.get('NonCompliantCount', 0)

                    # Get severity breakdown for non-compliant patches
                    non_compliant_severity = non_compliant_summary.get('SeveritySummary', {})
                    compliance_summary['critical_count'] = non_compliant_severity.get('CriticalCount', 0)
                    compliance_summary['high_count'] = non_compliant_severity.get('HighCount', 0)
                    compliance_summary['medium_count'] = non_compliant_severity.get('MediumCount', 0)
                    compliance_summary['low_count'] = non_compliant_severity.get('LowCount', 0)
                    compliance_summary['informational_count'] = non_compliant_severity.get('InformationalCount', 0)
                    compliance_summary['unspecified_count'] = non_compliant_severity.get('UnspecifiedCount', 0)

            return compliance_summary

        except Exception as e:
            logger.error(f"Error getting patch compliance summary: {str(e)}")
            return {
                'compliant_instances': 0,
                'non_compliant_instances': 0,
                'critical_count': 0,
                'high_count': 0,
                'medium_count': 0,
                'low_count': 0,
                'informational_count': 0,
                'unspecified_count': 0
            }

    def get_detailed_noncompliance_counts_from_patch_states(self, session: boto3.Session) -> Dict:
        """Get detailed noncompliance counts using DescribeInstancePatchStates API (same as console uses)"""
        try:
            ssm_client = session.client('ssm')

            # Get all SSM managed instances first
            managed_instances = []
            try:
                paginator = ssm_client.get_paginator('describe_instance_information')
                for page in paginator.paginate():
                    for instance in page['InstanceInformationList']:
                        if instance.get('PingStatus') == 'Online':
                            managed_instances.append(instance['InstanceId'])
            except Exception as ssm_error:
                logger.warning(f"Error getting SSM instances for patch states: {str(ssm_error)}")
                return self.get_empty_noncompliance_counts()

            if not managed_instances:
                return self.get_empty_noncompliance_counts()

            compliance_details = {
                'missing_count': 0,
                'failed_count': 0,
                'installed_pending_reboot_count': 0,
                'installed_other_count': 0,
                'installed_rejected_count': 0,
                'not_applicable_count': 0
            }

            # Process instances in batches to get patch states (same as console does)
            batch_size = 50
            for i in range(0, len(managed_instances), batch_size):
                batch = managed_instances[i:i+batch_size]

                try:
                    response = ssm_client.describe_instance_patch_states(
                        InstanceIds=batch
                    )

                    for state in response.get('InstancePatchStates', []):
                        # Aggregate patch counts exactly as the console does
                        compliance_details['missing_count'] += max(0, state.get('MissingCount', 0))
                        compliance_details['failed_count'] += max(0, state.get('FailedCount', 0))
                        compliance_details['installed_pending_reboot_count'] += max(0, state.get('InstalledPendingRebootCount', 0))
                        compliance_details['installed_other_count'] += max(0, state.get('InstalledOtherCount', 0))
                        compliance_details['installed_rejected_count'] += max(0, state.get('InstalledRejectedCount', 0))
                        compliance_details['not_applicable_count'] += max(0, state.get('NotApplicableCount', 0))

                except Exception as batch_error:
                    logger.warning(f"Error processing patch states batch {i}-{i+batch_size}: {str(batch_error)}")
                    continue

            return compliance_details

        except Exception as e:
            logger.error(f"Error getting detailed noncompliance counts: {str(e)}")
            return self.get_empty_noncompliance_counts()

    def get_empty_noncompliance_counts(self) -> Dict:
        """Return empty noncompliance counts structure"""
        return {
            'missing_count': 0,
            'failed_count': 0,
            'installed_pending_reboot_count': 0,
            'installed_other_count': 0,
            'installed_rejected_count': 0,
            'not_applicable_count': 0
        }

    def collect_compliance_data(self, accounts: List[Dict]) -> Dict:
        """Collect patch compliance data using the exact same APIs as AWS console dashboards"""
        all_data = {
            'accounts': {},
            'generation_time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            # Organization-level summaries (matching AWS console exactly)
            'organization_summary': {
                'total_ec2_instances': 0,
                'managed_instances': 0,
                'not_managed_instances': 0,
                'managed_percentage': 0.0,
                'compliant_instances': 0,
                'non_compliant_instances': 0,
                'critical_count': 0,
                'high_count': 0,
                'medium_count': 0,
                'low_count': 0,
                'informational_count': 0,
                'unspecified_count': 0,
                'missing_count': 0,
                'failed_count': 0,
                'installed_pending_reboot_count': 0,
                'installed_other_count': 0,
                'installed_rejected_count': 0,
                'not_applicable_count': 0
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

            account_has_data = False

            for region in self.regions:
                logger.info(f"Processing region: {region}")

                # Assume role in target account
                session = self.assume_cross_account_role(account_id, region)
                if not session:
                    continue

                # Get instance management summary using Explorer APIs (GetOpsSummary)
                instance_mgmt_summary = self.get_instance_management_summary_from_explorer(session)

                # Skip regions with no EC2 instances
                if instance_mgmt_summary['total_ec2_instances'] == 0:
                    logger.info(f"No EC2 instances found in {account_name} - {region}")
                    continue

                account_has_data = True

                # Get patch compliance summary using Fleet Manager APIs (ListComplianceSummaries)
                patch_compliance_summary = self.get_patch_compliance_summary_from_compliance_api(session)

                # Get detailed noncompliance counts using patch states API
                detailed_compliance = self.get_detailed_noncompliance_counts_from_patch_states(session)

                region_data = {
                    # Instance management data (from Explorer/GetOpsSummary)
                    'total_ec2_instances': instance_mgmt_summary['total_ec2_instances'],
                    'managed_instances': instance_mgmt_summary['managed_instances'],
                    'not_managed_instances': instance_mgmt_summary['not_managed_instances'],
                    'managed_percentage': instance_mgmt_summary['managed_percentage'],

                    # Patch compliance data (from Fleet Manager/ListComplianceSummaries)
                    'compliant_instances': patch_compliance_summary['compliant_instances'],
                    'non_compliant_instances': patch_compliance_summary['non_compliant_instances'],
                    'critical_count': patch_compliance_summary['critical_count'],
                    'high_count': patch_compliance_summary['high_count'],
                    'medium_count': patch_compliance_summary['medium_count'],
                    'low_count': patch_compliance_summary['low_count'],
                    'informational_count': patch_compliance_summary['informational_count'],
                    'unspecified_count': patch_compliance_summary['unspecified_count'],

                    # Detailed compliance breakdown (from DescribeInstancePatchStates)
                    'missing_count': detailed_compliance['missing_count'],
                    'failed_count': detailed_compliance['failed_count'],
                    'installed_pending_reboot_count': detailed_compliance['installed_pending_reboot_count'],
                    'installed_other_count': detailed_compliance['installed_other_count'],
                    'installed_rejected_count': detailed_compliance['installed_rejected_count'],
                    'not_applicable_count': detailed_compliance['not_applicable_count']
                }

                account_data['regions'][region] = region_data

                # Update organization totals
                org_summary = all_data['organization_summary']
                org_summary['total_ec2_instances'] += instance_mgmt_summary['total_ec2_instances']
                org_summary['managed_instances'] += instance_mgmt_summary['managed_instances']
                org_summary['not_managed_instances'] += instance_mgmt_summary['not_managed_instances']
                org_summary['compliant_instances'] += patch_compliance_summary['compliant_instances']
                org_summary['non_compliant_instances'] += patch_compliance_summary['non_compliant_instances']
                org_summary['critical_count'] += patch_compliance_summary['critical_count']
                org_summary['high_count'] += patch_compliance_summary['high_count']
                org_summary['medium_count'] += patch_compliance_summary['medium_count']
                org_summary['low_count'] += patch_compliance_summary['low_count']
                org_summary['informational_count'] += patch_compliance_summary['informational_count']
                org_summary['unspecified_count'] += patch_compliance_summary['unspecified_count']
                org_summary['missing_count'] += detailed_compliance['missing_count']
                org_summary['failed_count'] += detailed_compliance['failed_count']
                org_summary['installed_pending_reboot_count'] += detailed_compliance['installed_pending_reboot_count']
                org_summary['installed_other_count'] += detailed_compliance['installed_other_count']
                org_summary['installed_rejected_count'] += detailed_compliance['installed_rejected_count']
                org_summary['not_applicable_count'] += detailed_compliance['not_applicable_count']

            # Only include accounts that have data
            if account_has_data:
                all_data['accounts'][account_id] = account_data

        # Calculate organization-level percentages
        org_summary = all_data['organization_summary']
        total_instances = org_summary['total_ec2_instances']
        managed_instances = org_summary['managed_instances']

        if total_instances > 0:
            org_summary['managed_percentage'] = round((managed_instances / total_instances) * 100, 1)

        return all_data

    def generate_aws_console_format_report(self, compliance_data: Dict) -> str:
        """Generate HTML email that exactly matches AWS Systems Manager dashboard format"""

        org_summary = compliance_data['organization_summary']

        # Calculate compliance percentages (based on managed instances only, same as console)
        managed_instances = org_summary['managed_instances']
        compliant_instances = org_summary['compliant_instances']
        non_compliant_instances = org_summary['non_compliant_instances']

        compliant_pct = round((compliant_instances / max(1, managed_instances)) * 100, 1) if managed_instances > 0 else 0.0
        non_compliant_pct = round((non_compliant_instances / max(1, managed_instances)) * 100, 1) if managed_instances > 0 else 0.0

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
                .note {{ background-color: #f0f8ff; padding: 10px; margin: 10px 0; font-size: 14px; }}
            </style>
        </head>
        <body>
            <h1>AWS Patch Compliance Report</h1>
            <p>Generated: {compliance_data['generation_time']}</p>
            <p>Organization: Multi-Account AWS Organization</p>
            <p>Regions: {', '.join(self.regions)}</p>

            <div class="note">
                <strong>Data Sources (Same as AWS Console):</strong>
                <br>• Instance management: GetOpsSummary API with AWS:EC2InstanceInformation (Explorer dashboard)
                <br>• Compliance summary: ListComplianceSummaries API (Fleet Manager dashboard)  
                <br>• Detailed breakdown: DescribeInstancePatchStates API (Patch Manager dashboard)
            </div>

            <div class="section">
                <h2>Amazon EC2 instance management</h2>
                <table>
                    <tr>
                        <th>Status</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                    <tr>
                        <td>Total EC2 Instances</td>
                        <td>{org_summary['total_ec2_instances']}</td>
                        <td>100.0%</td>
                    </tr>
                    <tr>
                        <td>Managed by Systems Manager</td>
                        <td>{org_summary['managed_instances']}</td>
                        <td>{org_summary['managed_percentage']}%</td>
                    </tr>
                    <tr>
                        <td>Not Managed by Systems Manager</td>
                        <td>{org_summary['not_managed_instances']}</td>
                        <td>{round(100 - org_summary['managed_percentage'], 1)}%</td>
                    </tr>
                </table>
            </div>

            <div class="section">
                <h2>Compliance summary (Managed Instances)</h2>
                <table>
                    <tr>
                        <th>Compliance Status</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                    <tr>
                        <td>Total Managed Instances</td>
                        <td>{managed_instances}</td>
                        <td>100.0%</td>
                    </tr>
                    <tr>
                        <td>Compliant</td>
                        <td>{compliant_instances}</td>
                        <td>{compliant_pct}%</td>
                    </tr>
                    <tr>
                        <td>Non-Compliant</td>
                        <td>{non_compliant_instances}</td>
                        <td>{non_compliant_pct}%</td>
                    </tr>
                </table>
            </div>

            <div class="section">
                <h2>Noncompliance counts</h2>
                <table>
                    <tr>
                        <th>Noncompliance Type</th>
                        <th>Count</th>
                    </tr>
                    <tr>
                        <td>Missing</td>
                        <td>{org_summary['missing_count']}</td>
                    </tr>
                    <tr>
                        <td>Failed</td>
                        <td>{org_summary['failed_count']}</td>
                    </tr>
                    <tr>
                        <td>Installed (Pending Reboot)</td>
                        <td>{org_summary['installed_pending_reboot_count']}</td>
                    </tr>
                    <tr>
                        <td>Installed (Other)</td>
                        <td>{org_summary['installed_other_count']}</td>
                    </tr>
                    <tr>
                        <td>Installed (Rejected)</td>
                        <td>{org_summary['installed_rejected_count']}</td>
                    </tr>
                    <tr>
                        <td>Not Applicable</td>
                        <td>{org_summary['not_applicable_count']}</td>
                    </tr>
                </table>
            </div>

            <div class="section">
                <h2>Severity Breakdown (Non-Compliant)</h2>
                <table>
                    <tr>
                        <th>Severity</th>
                        <th>Count</th>
                    </tr>
                    <tr>
                        <td>Critical</td>
                        <td>{org_summary['critical_count']}</td>
                    </tr>
                    <tr>
                        <td>High</td>
                        <td>{org_summary['high_count']}</td>
                    </tr>
                    <tr>
                        <td>Medium</td>
                        <td>{org_summary['medium_count']}</td>
                    </tr>
                    <tr>
                        <td>Low</td>
                        <td>{org_summary['low_count']}</td>
                    </tr>
                    <tr>
                        <td>Informational</td>
                        <td>{org_summary['informational_count']}</td>
                    </tr>
                    <tr>
                        <td>Unspecified</td>
                        <td>{org_summary['unspecified_count']}</td>
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
                        <th>Total EC2</th>
                        <th>Managed</th>
                        <th>Managed %</th>
                        <th>Compliant</th>
                        <th>Non-Compliant</th>
                        <th>Critical</th>
                        <th>Missing</th>
                        <th>Failed</th>
                        <th>Pending Reboot</th>
                    </tr>
            """

            for account_id, account_data in compliance_data['accounts'].items():
                account_name = account_data['account_name']

                for region, region_data in account_data['regions'].items():
                    html += f"""
                        <tr>
                            <td>{account_name}</td>
                            <td>{account_id}</td>
                            <td>{region}</td>
                            <td>{region_data['total_ec2_instances']}</td>
                            <td>{region_data['managed_instances']}</td>
                            <td>{region_data['managed_percentage']}%</td>
                            <td>{region_data['compliant_instances']}</td>
                            <td>{region_data['non_compliant_instances']}</td>
                            <td>{region_data['critical_count']}</td>
                            <td>{region_data['missing_count']}</td>
                            <td>{region_data['failed_count']}</td>
                            <td>{region_data['installed_pending_reboot_count']}</td>
                        </tr>
                    """

            html += """
                </table>
            </div>
            """

        html += """
            <p>This report was generated using the exact same APIs as AWS Systems Manager console dashboards.</p>
            <p>Report generated by AWS Patch Compliance Reporter Lambda function.</p>
        </body>
        </html>
        """

        return html

    def generate_and_send_report(self, compliance_data: Dict):
        """Generate and send email report matching AWS console format exactly"""
        try:
            # Generate HTML report
            html_body = self.generate_aws_console_format_report(compliance_data)

            # Prepare email subject
            org_summary = compliance_data['organization_summary']
            managed_instances = org_summary['managed_instances']
            compliant_instances = org_summary['compliant_instances']
            compliant_pct = round((compliant_instances / max(1, managed_instances)) * 100, 1) if managed_instances > 0 else 0.0

            subject = f"AWS Patch Compliance Report - {org_summary['total_ec2_instances']} total, {managed_instances} managed, {compliant_instances} compliant ({compliant_pct}%)"

            # Send email using your SES module
            # Uncomment and modify based on your SES setup:
            # send_email(
            #     sender_address=self.sender_email,
            #     receiver_addresses=self.recipient_emails,
            #     subject=subject,
            #     body=html_body
            # )

            logger.info(f"Email report generated successfully")
            logger.info(f"Subject: {subject}")

        except Exception as e:
            logger.error(f"Error generating email report: {str(e)}")
            raise

# Lambda handler entry point
def lambda_handler(event, context):
    reporter = PatchComplianceReporter()
    return reporter.lambda_handler(event, context)
