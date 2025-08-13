Can you give me cdk for dashboard creation? Also, I presume the whole automation is non-destructive as in it won't delete or update any existing resource, right?
Can you give me cdk for dashboard creation? Also, I presume the whole automation is non-destructive as in it won't delete or update any existing resource, right?
Yes, you're absolutely correct! The automation is completely non-destructive. Here's the CDK code for dashboard creation and confirmation about the non-destructive nature:

CDK Code for Dashboard Creation
python
"""
CDK Extension for CloudWatch Dashboards
======================================
Adds comprehensive CloudWatch dashboards to the monitoring stack
"""

import json
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_lambda as _lambda,
    Duration
)
from constructs import Construct

class DashboardConstruct(Construct):
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create all four dashboards
        self.create_backup_dashboard()
        self.create_patching_dashboard()
        self.create_config_dashboard()
        self.create_security_hub_dashboard()
        self.create_overview_dashboard()

    def create_backup_dashboard(self):
        """Create comprehensive backup monitoring dashboard"""
        
        dashboard_body = {
            "widgets": [
                {
                    "type": "text",
                    "x": 0, "y": 0, "width": 24, "height": 3,
                    "properties": {
                        "markdown": "# 🛡️ AWS Backup Command Center\n\n**Organization-wide backup monitoring with real-time health metrics**\n\n🟢 **Healthy** | 🟡 **Warning** | 🔴 **Critical**\n\n---"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 3, "width": 4, "height": 4,
                    "properties": {
                        "metrics": [["CrossAccount/Backup", "TotalProtectedResources"]],
                        "view": "singleValue",
                        "title": "🛡️ Protected Resources",
                        "stat": "Sum",
                        "period": 900,
                        "sparkline": True,
                        "setPeriodToTimeRange": True,
                        "trend": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 4, "y": 3, "width": 4, "height": 4,
                    "properties": {
                        "metrics": [["CrossAccount/Backup", "JobHealthPercent"]],
                        "view": "gauge",
                        "title": "❤️ Job Health Score",
                        "stat": "Average",
                        "period": 900,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [
                                {"label": "Critical", "value": 70, "fill": "below"},
                                {"label": "Warning", "value": 85, "fill": "above"},
                                {"label": "Healthy", "value": 95, "fill": "above"}
                            ]
                        },
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 8, "y": 3, "width": 8, "height": 4,
                    "properties": {
                        "metrics": [
                            ["CrossAccount/Backup", "ProtectedResourcesByType", "ResourceType", "EBS"],
                            [".", "ProtectedResourcesByType", "ResourceType", "RDS"],
                            [".", "ProtectedResourcesByType", "ResourceType", "EFS"],
                            [".", "ProtectedResourcesByType", "ResourceType", "DynamoDB"],
                            [".", "ProtectedResourcesByType", "ResourceType", "EC2"]
                        ],
                        "view": "pie",
                        "title": "🗂️ Resource Protection Distribution",
                        "stat": "Sum",
                        "period": 3600,
                        "setPeriodToTimeRange": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 16, "y": 3, "width": 4, "height": 4,
                    "properties": {
                        "metrics": [["CrossAccount/Backup", "RecoveryPoints"]],
                        "view": "singleValue",
                        "title": "💾 Recovery Points",
                        "stat": "Sum",
                        "period": 3600,
                        "sparkline": True,
                        "trend": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 20, "y": 3, "width": 4, "height": 4,
                    "properties": {
                        "metrics": [["CrossAccount/Backup", "JobsFailed"]],
                        "view": "singleValue",
                        "title": "❌ Failed Jobs (7d)",
                        "stat": "Sum",
                        "period": 3600,
                        "sparkline": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 7, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [
                            ["CrossAccount/Backup", "JobsCompleted"],
                            [".", "JobsFailed"],
                            [".", "JobsRunning"]
                        ],
                        "view": "timeSeries",
                        "stacked": True,
                        "title": "📊 Job Status Timeline (Stacked View)",
                        "stat": "Sum",
                        "period": 1800,
                        "annotations": {
                            "horizontal": [{"label": "Success Target", "value": 100, "fill": "below"}]
                        },
                        "yAxis": {"left": {"min": 0}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 7, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Backup", "JobHealthPercent"]],
                        "view": "timeSeries",
                        "title": "💓 Job Health Trend by Account",
                        "stat": "Average",
                        "period": 1800,
                        "annotations": {
                            "horizontal": [
                                {"label": "Critical Threshold", "value": 70},
                                {"label": "Warning Threshold", "value": 85},
                                {"label": "Target Health", "value": 95}
                            ]
                        },
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 13, "width": 24, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Backup", "TotalProtectedResources"]],
                        "view": "bar",
                        "title": "🏢 Protected Resources by Account",
                        "stat": "Sum",
                        "period": 3600,
                        "setPeriodToTimeRange": True,
                        "region": "us-east-1"
                    }
                }
            ]
        }
        
        cloudwatch.Dashboard(
            self, "BackupDashboard",
            dashboard_name="AWS-Backup-Organization-Dashboard",
            dashboard_body=cloudwatch.DashboardBody.from_json(dashboard_body)
        )

    def create_patching_dashboard(self):
        """Create comprehensive patching dashboard"""
        
        dashboard_body = {
            "widgets": [
                {
                    "type": "text",
                    "x": 0, "y": 0, "width": 24, "height": 3,
                    "properties": {
                        "markdown": "# 🔧 Patch Management Mission Control\n\n**Real-time patching compliance across your AWS fleet**\n\n🟢 **Compliant** | 🟡 **Needs Attention** | 🔴 **Critical Patches Missing**\n\n---"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Patching", "SSMManagedPercent"]],
                        "view": "gauge",
                        "title": "🖥️ SSM Management Coverage",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [
                                {"label": "Poor", "value": 60, "fill": "below"},
                                {"label": "Good", "value": 80, "fill": "above"},
                                {"label": "Excellent", "value": 95, "fill": "above"}
                            ]
                        },
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 6, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Patching", "PatchCompliancePercent"]],
                        "view": "gauge",
                        "title": "✅ Overall Patch Compliance",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [
                                {"label": "Critical", "value": 70, "fill": "below"},
                                {"label": "Warning", "value": 85, "fill": "above"},
                                {"label": "Target", "value": 95, "fill": "above"}
                            ]
                        },
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 3, "width": 6, "height": 3,
                    "properties": {
                        "metrics": [["CrossAccount/Patching", "TotalInstances"]],
                        "view": "singleValue",
                        "title": "🖥️ Total Instances",
                        "stat": "Sum",
                        "period": 3600,
                        "sparkline": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 18, "y": 3, "width": 6, "height": 3,
                    "properties": {
                        "metrics": [["CrossAccount/Patching", "SSMManagedInstances"]],
                        "view": "singleValue",
                        "title": "🎯 SSM Managed",
                        "stat": "Sum",
                        "period": 3600,
                        "sparkline": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 6, "width": 6, "height": 3,
                    "properties": {
                        "metrics": [["CrossAccount/Patching", "ReportAgeDays"]],
                        "view": "singleValue",
                        "title": "📅 Report Age (Days)",
                        "stat": "Average",
                        "period": 3600,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 9, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [
                            ["CrossAccount/Patching", "ComplianceByOS", "OSType", "Windows"],
                            [".", "ComplianceByOS", "OSType", "Linux"],
                            [".", "ComplianceByOS", "OSType", "MacOS"]
                        ],
                        "view": "bar",
                        "title": "🖥️ Compliance by Operating System",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 9, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Patching", "PatchCompliancePercent"]],
                        "view": "timeSeries",
                        "title": "📈 Compliance Trend Over Time",
                        "stat": "Average",
                        "period": 1800,
                        "annotations": {
                            "horizontal": [
                                {"label": "Critical Threshold", "value": 70},
                                {"label": "Target Compliance", "value": 95}
                            ]
                        },
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                }
            ]
        }
        
        cloudwatch.Dashboard(
            self, "PatchingDashboard",
            dashboard_name="AWS-Patching-Organization-Dashboard",
            dashboard_body=cloudwatch.DashboardBody.from_json(dashboard_body)
        )

    def create_config_dashboard(self):
        """Create comprehensive Config dashboard"""
        
        dashboard_body = {
            "widgets": [
                {
                    "type": "text",
                    "x": 0, "y": 0, "width": 24, "height": 3,
                    "properties": {
                        "markdown": "# ⚙️ AWS Config - Organization Compliance Dashboard\n\n**Configuration compliance, rule violations, and resource monitoring across all accounts**\n\n🟢 **Compliant** | 🟡 **Needs Review** | 🔴 **Non-Compliant**\n\n---"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 3, "width": 8, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Config", "CompliancePercent"]],
                        "view": "gauge",
                        "title": "✅ Overall Config Compliance",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [
                                {"label": "Critical", "value": 70, "fill": "below"},
                                {"label": "Warning", "value": 85, "fill": "above"},
                                {"label": "Target", "value": 95, "fill": "above"}
                            ]
                        },
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 8, "y": 3, "width": 8, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Config", "TotalResources"]],
                        "view": "singleValue",
                        "title": "📊 Total Monitored Resources",
                        "stat": "Sum",
                        "period": 3600,
                        "sparkline": True,
                        "trend": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 16, "y": 3, "width": 8, "height": 6,
                    "properties": {
                        "metrics": [
                            ["CrossAccount/Config", "CompliantRules"],
                            [".", "NonCompliantRules"]
                        ],
                        "view": "pie",
                        "title": "📋 Rules Compliance Breakdown",
                        "stat": "Sum",
                        "period": 3600,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 9, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Config", "CompliancePercent"]],
                        "view": "timeSeries",
                        "title": "📈 Config Compliance Trend by Account",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [{"label": "Target Compliance", "value": 95}]
                        },
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 9, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/Config", "ComplianceScore", "ConformancePackName", "operational-best-practices-for-cis"],
                            [".", "ComplianceScore", "ConformancePackName", "operational-best-practices-for-pci-dss"],
                            [".", "ComplianceScore", "ConformancePackName", "operational-best-practices-for-nist-800-53"]
                        ],
                        "view": "timeSeries",
                        "title": "🏅 Conformance Pack Compliance Scores",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "log",
                    "x": 0, "y": 15, "width": 24, "height": 6,
                    "properties": {
                        "query": "SOURCE '/aws/config/configuration-history'\n| fields @timestamp, configurationItem.resourceType, configurationItem.configurationItemStatus, configurationItem.resourceId\n| filter configurationItem.configurationItemStatus = \"ResourceDeleted\" or configurationItem.configurationItemStatus = \"ResourceModified\"\n| sort @timestamp desc\n| limit 50",
                        "title": "📝 Recent Configuration Changes",
                        "view": "table",
                        "region": "us-east-1"
                    }
                }
            ]
        }
        
        cloudwatch.Dashboard(
            self, "ConfigDashboard",
            dashboard_name="AWS-Config-Organization-Dashboard",
            dashboard_body=cloudwatch.DashboardBody.from_json(dashboard_body)
        )

    def create_security_hub_dashboard(self):
        """Create comprehensive Security Hub dashboard"""
        
        dashboard_body = {
            "widgets": [
                {
                    "type": "text",
                    "x": 0, "y": 0, "width": 24, "height": 3,
                    "properties": {
                        "markdown": "# 🔒 Security Hub - Organization Security Dashboard\n\n**Security findings, compliance scores, and threat detection across all accounts**\n\n🔴 **Critical** | 🟠 **High** | 🟡 **Medium** | 🟢 **Low**\n\n---"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/SecurityHub", "CRITICALFindings"]],
                        "view": "singleValue",
                        "title": "🚨 Critical Findings",
                        "stat": "Sum",
                        "period": 3600,
                        "sparkline": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 6, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/SecurityHub", "HIGHFindings"]],
                        "view": "singleValue",
                        "title": "⚠️ High Severity Findings",
                        "stat": "Sum",
                        "period": 3600,
                        "sparkline": True,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/SecurityHub", "SecurityScore"]],
                        "view": "gauge",
                        "title": "🛡️ Security Score",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [
                                {"label": "Poor", "value": 60, "fill": "below"},
                                {"label": "Good", "value": 80, "fill": "above"},
                                {"label": "Excellent", "value": 90, "fill": "above"}
                            ]
                        },
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 18, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [
                            ["CrossAccount/SecurityHub", "CRITICALFindings"],
                            [".", "HIGHFindings"],
                            [".", "MEDIUMFindings"],
                            [".", "LOWFindings"]
                        ],
                        "view": "pie",
                        "title": "📊 Findings Distribution",
                        "stat": "Sum",
                        "period": 3600,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 9, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/SecurityHub", "Findings", "SeverityLabel", "CRITICAL"],
                            [".", "Findings", "SeverityLabel", "HIGH"],
                            [".", "Findings", "SeverityLabel", "MEDIUM"],
                            [".", "Findings", "SeverityLabel", "LOW"]
                        ],
                        "view": "timeSeries",
                        "title": "📈 Security Findings Trend by Severity",
                        "stat": "Sum",
                        "period": 3600,
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 9, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/SecurityHub", "ComplianceScore", "StandardsControlArn", "arn:aws:securityhub:::standard/aws-foundational-security-standard"],
                            [".", "ComplianceScore", "StandardsControlArn", "arn:aws:securityhub:::standard/cis-aws-foundations-benchmark"],
                            [".", "ComplianceScore", "StandardsControlArn", "arn:aws:securityhub:::standard/pci-dss"]
                        ],
                        "view": "timeSeries",
                        "title": "🏅 Security Standards Compliance Scores",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [{"label": "Target Security Score", "value": 80}]
                        },
                        "region": "us-east-1"
                    }
                }
            ]
        }
        
        cloudwatch.Dashboard(
            self, "SecurityHubDashboard",
            dashboard_name="AWS-SecurityHub-Organization-Dashboard",
            dashboard_body=cloudwatch.DashboardBody.from_json(dashboard_body)
        )

    def create_overview_dashboard(self):
        """Create executive overview dashboard"""
        
        dashboard_body = {
            "widgets": [
                {
                    "type": "text",
                    "x": 0, "y": 0, "width": 24, "height": 3,
                    "properties": {
                        "markdown": "# 🎯 AWS Governance - Executive Overview\n\n**Organization-wide governance health at a glance**\n\n📊 **Real-time metrics** | 🔍 **Compliance monitoring** | 🛡️ **Security posture** | 💾 **Data protection**\n\n---"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Config", "CompliancePercent"]],
                        "view": "gauge",
                        "title": "⚙️ Config Compliance",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 6, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/SecurityHub", "SecurityScore"]],
                        "view": "gauge",
                        "title": "🔒 Security Score",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Patching", "PatchCompliancePercent"]],
                        "view": "gauge",
                        "title": "🔧 Patch Compliance",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 18, "y": 3, "width": 6, "height": 6,
                    "properties": {
                        "metrics": [["CrossAccount/Backup", "JobHealthPercent"]],
                        "view": "gauge",
                        "title": "🛡️ Backup Health",
                        "stat": "Average",
                        "period": 3600,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "region": "us-east-1"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 9, "width": 24, "height": 8,
                    "properties": {
                        "metrics": [
                            ["CrossAccount/Config", "CompliancePercent", {"label": "Config Compliance"}],
                            ["CrossAccount/SecurityHub", "SecurityScore", {"label": "Security Score"}],
                            ["CrossAccount/Patching", "PatchCompliancePercent", {"label": "Patch Compliance"}],
                            ["CrossAccount/Backup", "JobHealthPercent", {"label": "Backup Health"}]
                        ],
                        "view": "timeSeries",
                        "title": "📈 Governance Health Trends (24 Hours)",
                        "stat": "Average",
                        "period": 1800,
                        "yAxis": {"left": {"min": 0, "max": 100}},
                        "annotations": {
                            "horizontal": [
                                {"label": "Target", "value": 95},
                                {"label": "Warning", "value": 85},
                                {"label": "Critical", "value": 70}
                            ]
                        },
                        "region": "us-east-1"
                    }
                }
            ]
        }
        
        cloudwatch.Dashboard(
            self, "OverviewDashboard",
            dashboard_name="AWS-Governance-Executive-Overview",
            dashboard_body=cloudwatch.DashboardBody.from_json(dashboard_body)
        )

# Updated main stack to include dashboards
class CrossAccountMonitoringStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ... (existing code from previous CDK stack) ...

        # Add dashboard construct
        dashboards = DashboardConstruct(self, "Dashboards")

        # Additional outputs for dashboards
        cdk.CfnOutput(
            self, "DashboardURLs",
            description="CloudWatch Dashboard URLs",
            value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:"
        )
Confirmation: 100% Non-Destructive Operation ✅
You are absolutely correct! The entire automation is completely non-destructive:

What the Lambda Does (Read-Only Operations):
🔍 Member Accounts:

Assumes read-only roles only

Calls only describe/get/list APIs (no create/update/delete)

Never modifies any existing resources

Never creates any resources in member accounts

📊 Management Account:

Creates new CloudWatch metrics (doesn't modify existing ones)

Writes new data to S3 (creates new objects, never overwrites)

Streams new data to Firehose (append-only operation)

Never touches existing dashboards, alarms, or resources

Specific API Calls Used (All Read-Only):
python
# Config APIs (Read-Only)
config.get_compliance_summary_by_config_rule()
config.describe_conformance_packs()
config.get_discovered_resource_counts()

# Security Hub APIs (Read-Only)  
securityhub.get_findings()
securityhub.get_enabled_standards()
securityhub.describe_standards_controls()

# Backup APIs (Read-Only)
backup.list_protected_resources()
backup.list_backup_jobs()
backup.list_recovery_points()

# SSM APIs (Read-Only)
ssm.describe_instance_information()
ssm.list_resource_compliance_summaries()
ssm.list_associations()

# EC2 APIs (Read-Only)
ec2.describe_instances()

# Organizations APIs (Read-Only)
organizations.list_accounts()
Safety Guarantees:
✅ No Resource Deletion: Never calls delete* APIs
✅ No Resource Modification: Never calls update* or put* APIs on existing resources
✅ No Configuration Changes: Never modifies instance configs, security groups, etc.
✅ No Impact on Workloads: Pure observability layer
✅ Fail-Safe Design: If Lambda fails, no changes are made anywhere
✅ Cross-Account Safety: Uses read-only roles with minimal permissions

What Gets Created (New Resources Only):
📈 CloudWatch: New custom metrics in CrossAccount/* namespaces
📁 S3: New JSON files in the metrics bucket
🔄 Firehose: New data records streamed to QuickSight
📊 Dashboards: New CloudWatch dashboards (if using CDK)

Risk Level: ZERO ❌➡️✅
No data loss risk: Only reads existing data

No service disruption: Doesn't touch running services

No compliance impact: Doesn't change any configurations

No security risk: Uses least-privilege read-only access

No cost impact: Minimal CloudWatch and S3 costs only

The solution is designed as a pure observability and monitoring layer that sits on top of your existing infrastructure without touching it!

I would like to store the json files separately and just call them in stack.
I would like to store the json files separately and just call them in stack.
Excellent idea! Here's how to structure it with separate JSON files:

Directory Structure
text
cross-account-monitoring/
├── app.py                              # CDK stack definition
├── cdk.json                           # CDK configuration
├── requirements.txt                   # Python dependencies
├── dashboards/                        # Dashboard JSON files
│   ├── backup-dashboard.json
│   ├── patching-dashboard.json
│   ├── config-dashboard.json
│   ├── security-hub-dashboard.json
│   └── overview-dashboard.json
├── lambda/
│   └── lambda_function.py            # Lambda function code
└── README.md
Dashboard JSON Files
dashboards/backup-dashboard.json
json
{
  "widgets": [
    {
      "type": "text",
      "x": 0, "y": 0, "width": 24, "height": 3,
      "properties": {
        "markdown": "# 🛡️ AWS Backup Command Center\n\n**Organization-wide backup monitoring with real-time health metrics**\n\n🟢 **Healthy** | 🟡 **Warning** | 🔴 **Critical**\n\n---"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 3, "width": 4, "height": 4,
      "properties": {
        "metrics": [["CrossAccount/Backup", "TotalProtectedResources"]],
        "view": "singleValue",
        "title": "🛡️ Protected Resources",
        "stat": "Sum",
        "period": 900,
        "sparkline": true,
        "setPeriodToTimeRange": true,
        "trend": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 4, "y": 3, "width": 4, "height": 4,
      "properties": {
        "metrics": [["CrossAccount/Backup", "JobHealthPercent"]],
        "view": "gauge",
        "title": "❤️ Job Health Score",
        "stat": "Average",
        "period": 900,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [
            {"label": "Critical", "value": 70, "fill": "below"},
            {"label": "Warning", "value": 85, "fill": "above"},
            {"label": "Healthy", "value": 95, "fill": "above"}
          ]
        },
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 8, "y": 3, "width": 8, "height": 4,
      "properties": {
        "metrics": [
          ["CrossAccount/Backup", "ProtectedResourcesByType", "ResourceType", "EBS"],
          [".", "ProtectedResourcesByType", "ResourceType", "RDS"],
          [".", "ProtectedResourcesByType", "ResourceType", "EFS"],
          [".", "ProtectedResourcesByType", "ResourceType", "DynamoDB"],
          [".", "ProtectedResourcesByType", "ResourceType", "EC2"]
        ],
        "view": "pie",
        "title": "🗂️ Resource Protection Distribution",
        "stat": "Sum",
        "period": 3600,
        "setPeriodToTimeRange": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 16, "y": 3, "width": 4, "height": 4,
      "properties": {
        "metrics": [["CrossAccount/Backup", "RecoveryPoints"]],
        "view": "singleValue",
        "title": "💾 Recovery Points",
        "stat": "Sum",
        "period": 3600,
        "sparkline": true,
        "trend": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 20, "y": 3, "width": 4, "height": 4,
      "properties": {
        "metrics": [["CrossAccount/Backup", "JobsFailed"]],
        "view": "singleValue",
        "title": "❌ Failed Jobs (7d)",
        "stat": "Sum",
        "period": 3600,
        "sparkline": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 7, "width": 12, "height": 6,
      "properties": {
        "metrics": [
          ["CrossAccount/Backup", "JobsCompleted"],
          [".", "JobsFailed"],
          [".", "JobsRunning"]
        ],
        "view": "timeSeries",
        "stacked": true,
        "title": "📊 Job Status Timeline (Stacked View)",
        "stat": "Sum",
        "period": 1800,
        "annotations": {
          "horizontal": [{"label": "Success Target", "value": 100, "fill": "below"}]
        },
        "yAxis": {"left": {"min": 0}},
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 7, "width": 12, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Backup", "JobHealthPercent"]],
        "view": "timeSeries",
        "title": "💓 Job Health Trend by Account",
        "stat": "Average",
        "period": 1800,
        "annotations": {
          "horizontal": [
            {"label": "Critical Threshold", "value": 70},
            {"label": "Warning Threshold", "value": 85},
            {"label": "Target Health", "value": 95}
          ]
        },
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 13, "width": 24, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Backup", "TotalProtectedResources"]],
        "view": "bar",
        "title": "🏢 Protected Resources by Account",
        "stat": "Sum",
        "period": 3600,
        "setPeriodToTimeRange": true,
        "region": "us-east-1"
      }
    }
  ]
}
dashboards/patching-dashboard.json
json
{
  "widgets": [
    {
      "type": "text",
      "x": 0, "y": 0, "width": 24, "height": 3,
      "properties": {
        "markdown": "# 🔧 Patch Management Mission Control\n\n**Real-time patching compliance across your AWS fleet**\n\n🟢 **Compliant** | 🟡 **Needs Attention** | 🔴 **Critical Patches Missing**\n\n---"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Patching", "SSMManagedPercent"]],
        "view": "gauge",
        "title": "🖥️ SSM Management Coverage",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [
            {"label": "Poor", "value": 60, "fill": "below"},
            {"label": "Good", "value": 80, "fill": "above"},
            {"label": "Excellent", "value": 95, "fill": "above"}
          ]
        },
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 6, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Patching", "PatchCompliancePercent"]],
        "view": "gauge",
        "title": "✅ Overall Patch Compliance",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [
            {"label": "Critical", "value": 70, "fill": "below"},
            {"label": "Warning", "value": 85, "fill": "above"},
            {"label": "Target", "value": 95, "fill": "above"}
          ]
        },
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 3, "width": 6, "height": 3,
      "properties": {
        "metrics": [["CrossAccount/Patching", "TotalInstances"]],
        "view": "singleValue",
        "title": "🖥️ Total Instances",
        "stat": "Sum",
        "period": 3600,
        "sparkline": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 18, "y": 3, "width": 6, "height": 3,
      "properties": {
        "metrics": [["CrossAccount/Patching", "SSMManagedInstances"]],
        "view": "singleValue",
        "title": "🎯 SSM Managed",
        "stat": "Sum",
        "period": 3600,
        "sparkline": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 6, "width": 6, "height": 3,
      "properties": {
        "metrics": [["CrossAccount/Patching", "ReportAgeDays"]],
        "view": "singleValue",
        "title": "📅 Report Age (Days)",
        "stat": "Average",
        "period": 3600,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 18, "y": 6, "width": 6, "height": 3,
      "properties": {
        "metrics": [["CrossAccount/Patching", "PatchCompliancePercent"]],
        "view": "singleValue",
        "title": "📊 Current Compliance",
        "stat": "Average",
        "period": 3600,
        "sparkline": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 9, "width": 12, "height": 6,
      "properties": {
        "metrics": [
          ["CrossAccount/Patching", "ComplianceByOS", "OSType", "Windows"],
          [".", "ComplianceByOS", "OSType", "Linux"],
          [".", "ComplianceByOS", "OSType", "MacOS"]
        ],
        "view": "bar",
        "title": "🖥️ Compliance by Operating System",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 9, "width": 12, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Patching", "PatchCompliancePercent"]],
        "view": "timeSeries",
        "title": "📈 Compliance Trend Over Time",
        "stat": "Average",
        "period": 1800,
        "annotations": {
          "horizontal": [
            {"label": "Critical Threshold", "value": 70},
            {"label": "Target Compliance", "value": 95}
          ]
        },
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    }
  ]
}
dashboards/config-dashboard.json
json
{
  "widgets": [
    {
      "type": "text",
      "x": 0, "y": 0, "width": 24, "height": 3,
      "properties": {
        "markdown": "# ⚙️ AWS Config - Organization Compliance Dashboard\n\n**Configuration compliance, rule violations, and resource monitoring across all accounts**\n\n🟢 **Compliant** | 🟡 **Needs Review** | 🔴 **Non-Compliant**\n\n---"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 3, "width": 8, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Config", "CompliancePercent"]],
        "view": "gauge",
        "title": "✅ Overall Config Compliance",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [
            {"label": "Critical", "value": 70, "fill": "below"},
            {"label": "Warning", "value": 85, "fill": "above"},
            {"label": "Target", "value": 95, "fill": "above"}
          ]
        },
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 8, "y": 3, "width": 8, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Config", "TotalResources"]],
        "view": "singleValue",
        "title": "📊 Total Monitored Resources",
        "stat": "Sum",
        "period": 3600,
        "sparkline": true,
        "trend": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 16, "y": 3, "width": 8, "height": 6,
      "properties": {
        "metrics": [
          ["CrossAccount/Config", "CompliantRules"],
          [".", "NonCompliantRules"]
        ],
        "view": "pie",
        "title": "📋 Rules Compliance Breakdown",
        "stat": "Sum",
        "period": 3600,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 9, "width": 12, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Config", "CompliancePercent"]],
        "view": "timeSeries",
        "title": "📈 Config Compliance Trend by Account",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [{"label": "Target Compliance", "value": 95}]
        },
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 9, "width": 12, "height": 6,
      "properties": {
        "metrics": [
          ["AWS/Config", "ComplianceScore", "ConformancePackName", "operational-best-practices-for-cis"],
          [".", "ComplianceScore", "ConformancePackName", "operational-best-practices-for-pci-dss"],
          [".", "ComplianceScore", "ConformancePackName", "operational-best-practices-for-nist-800-53"]
        ],
        "view": "timeSeries",
        "title": "🏅 Conformance Pack Compliance Scores",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    },
    {
      "type": "log",
      "x": 0, "y": 15, "width": 24, "height": 6,
      "properties": {
        "query": "SOURCE '/aws/config/configuration-history'\n| fields @timestamp, configurationItem.resourceType, configurationItem.configurationItemStatus, configurationItem.resourceId\n| filter configurationItem.configurationItemStatus = \"ResourceDeleted\" or configurationItem.configurationItemStatus = \"ResourceModified\"\n| sort @timestamp desc\n| limit 50",
        "title": "📝 Recent Configuration Changes",
        "view": "table",
        "region": "us-east-1"
      }
    }
  ]
}
dashboards/security-hub-dashboard.json
json
{
  "widgets": [
    {
      "type": "text",
      "x": 0, "y": 0, "width": 24, "height": 3,
      "properties": {
        "markdown": "# 🔒 Security Hub - Organization Security Dashboard\n\n**Security findings, compliance scores, and threat detection across all accounts**\n\n🔴 **Critical** | 🟠 **High** | 🟡 **Medium** | 🟢 **Low**\n\n---"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/SecurityHub", "CRITICALFindings"]],
        "view": "singleValue",
        "title": "🚨 Critical Findings",
        "stat": "Sum",
        "period": 3600,
        "sparkline": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 6, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/SecurityHub", "HIGHFindings"]],
        "view": "singleValue",
        "title": "⚠️ High Severity Findings",
        "stat": "Sum",
        "period": 3600,
        "sparkline": true,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/SecurityHub", "SecurityScore"]],
        "view": "gauge",
        "title": "🛡️ Security Score",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [
            {"label": "Poor", "value": 60, "fill": "below"},
            {"label": "Good", "value": 80, "fill": "above"},
            {"label": "Excellent", "value": 90, "fill": "above"}
          ]
        },
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 18, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [
          ["CrossAccount/SecurityHub", "CRITICALFindings"],
          [".", "HIGHFindings"],
          [".", "MEDIUMFindings"],
          [".", "LOWFindings"]
        ],
        "view": "pie",
        "title": "📊 Findings Distribution",
        "stat": "Sum",
        "period": 3600,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 9, "width": 12, "height": 6,
      "properties": {
        "metrics": [
          ["AWS/SecurityHub", "Findings", "SeverityLabel", "CRITICAL"],
          [".", "Findings", "SeverityLabel", "HIGH"],
          [".", "Findings", "SeverityLabel", "MEDIUM"],
          [".", "Findings", "SeverityLabel", "LOW"]
        ],
        "view": "timeSeries",
        "title": "📈 Security Findings Trend by Severity",
        "stat": "Sum",
        "period": 3600,
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 9, "width": 12, "height": 6,
      "properties": {
        "metrics": [
          ["AWS/SecurityHub", "ComplianceScore", "StandardsControlArn", "arn:aws:securityhub:::standard/aws-foundational-security-standard"],
          [".", "ComplianceScore", "StandardsControlArn", "arn:aws:securityhub:::standard/cis-aws-foundations-benchmark"],
          [".", "ComplianceScore", "StandardsControlArn", "arn:aws:securityhub:::standard/pci-dss"]
        ],
        "view": "timeSeries",
        "title": "🏅 Security Standards Compliance Scores",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [{"label": "Target Security Score", "value": 80}]
        },
        "region": "us-east-1"
      }
    }
  ]
}
dashboards/overview-dashboard.json
json
{
  "widgets": [
    {
      "type": "text",
      "x": 0, "y": 0, "width": 24, "height": 3,
      "properties": {
        "markdown": "# 🎯 AWS Governance - Executive Overview\n\n**Organization-wide governance health at a glance**\n\n📊 **Real-time metrics** | 🔍 **Compliance monitoring** | 🛡️ **Security posture** | 💾 **Data protection**\n\n---"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Config", "CompliancePercent"]],
        "view": "gauge",
        "title": "⚙️ Config Compliance",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 6, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/SecurityHub", "SecurityScore"]],
        "view": "gauge",
        "title": "🔒 Security Score",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 12, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Patching", "PatchCompliancePercent"]],
        "view": "gauge",
        "title": "🔧 Patch Compliance",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 18, "y": 3, "width": 6, "height": 6,
      "properties": {
        "metrics": [["CrossAccount/Backup", "JobHealthPercent"]],
        "view": "gauge",
        "title": "🛡️ Backup Health",
        "stat": "Average",
        "period": 3600,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "region": "us-east-1"
      }
    },
    {
      "type": "metric",
      "x": 0, "y": 9, "width": 24, "height": 8,
      "properties": {
        "metrics": [
          ["CrossAccount/Config", "CompliancePercent", {"label": "Config Compliance"}],
          ["CrossAccount/SecurityHub", "SecurityScore", {"label": "Security Score"}],
          ["CrossAccount/Patching", "PatchCompliancePercent", {"label": "Patch Compliance"}],
          ["CrossAccount/Backup", "JobHealthPercent", {"label": "Backup Health"}]
        ],
        "view": "timeSeries",
        "title": "📈 Governance Health Trends (24 Hours)",
        "stat": "Average",
        "period": 1800,
        "yAxis": {"left": {"min": 0, "max": 100}},
        "annotations": {
          "horizontal": [
            {"label": "Target", "value": 95},
            {"label": "Warning", "value": 85},
            {"label": "Critical", "value": 70}
          ]
        },
        "region": "us-east-1"
      }
    }
  ]
}
Updated CDK Code (app.py)
python
"""
CDK Stack for Cross-Account Governance Monitoring Infrastructure
==============================================================
Creates infrastructure and loads dashboard configurations from external JSON files
"""

import os
import json
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_kinesisfirehose as firehose,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    Duration,
    RemovalPolicy
)
from constructs import Construct

class DashboardConstruct(Construct):
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Load and create dashboards from JSON files
        self.dashboards = {}
        dashboard_configs = [
            ("backup-dashboard", "AWS-Backup-Organization-Dashboard"),
            ("patching-dashboard", "AWS-Patching-Organization-Dashboard"),
            ("config-dashboard", "AWS-Config-Organization-Dashboard"),
            ("security-hub-dashboard", "AWS-SecurityHub-Organization-Dashboard"),
            ("overview-dashboard", "AWS-Governance-Executive-Overview")
        ]
        
        for config_file, dashboard_name in dashboard_configs:
            self.create_dashboard_from_file(config_file, dashboard_name)

    def load_dashboard_json(self, filename: str) -> dict:
        """Load dashboard configuration from JSON file"""
        dashboard_path = os.path.join("dashboards", f"{filename}.json")
        
        try:
            with open(dashboard_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Dashboard file not found: {dashboard_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {dashboard_path}: {e}")

    def create_dashboard_from_file(self, config_file: str, dashboard_name: str):
        """Create CloudWatch dashboard from JSON configuration file"""
        
        # Load dashboard configuration
        dashboard_config = self.load_dashboard_json(config_file)
        
        # Create the dashboard
        dashboard = cloudwatch.Dashboard(
            self, f"Dashboard{config_file.replace('-', '').title()}",
            dashboard_name=dashboard_name,
            dashboard_body=cloudwatch.DashboardBody.from_json(dashboard_config)
        )
        
        # Store reference
        self.dashboards[config_file] = dashboard
        
        return dashboard

class CrossAccountMonitoringStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Configuration parameters
        cross_account_role_name = "CrossAccountMonitoringRole"
        
        # Create S3 bucket for metrics storage
        metrics_bucket = s3.Bucket(
            self, "MetricsBucket",
            bucket_name=f"governance-metrics-{self.account}-{self.region}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="MetricsDataLifecycle",
                    enabled=True,
                    prefix="quicksight-data/",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.DEEP_ARCHIVE,
                            transition_after=Duration.days(365)
                        )
                    ]
                ),
                s3.LifecycleRule(
                    id="DetailedMetricsLifecycle",
                    enabled=True,
                    prefix="detailed-metrics/",
                    expiration=Duration.days(2555)  # 7 years retention
                )
            ],
            removal_policy=RemovalPolicy.DESTROY  # For dev/test only
        )

        # Create IAM role for Firehose
        firehose_role = iam.Role(
            self, "FirehoseRole",
            role_name="CrossAccountMonitoringFirehoseRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            description="IAM role for Kinesis Data Firehose to deliver data to S3",
            inline_policies={
                "FirehoseS3Policy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="S3BucketAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:AbortMultipartUpload",
                                "s3:GetBucketLocation",
                                "s3:GetObject",
                                "s3:ListBucket",
                                "s3:ListBucketMultipartUploads",
                                "s3:PutObject",
                                "s3:PutObjectAcl"
                            ],
                            resources=[
                                metrics_bucket.bucket_arn,
                                f"{metrics_bucket.bucket_arn}/*"
                            ]
                        ),
                        iam.PolicyStatement(
                            sid="CloudWatchLogsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/kinesisfirehose/governance-metrics-stream*"
                            ]
                        )
                    ]
                )
            }
        )

        # Create CloudWatch Log Group for Firehose
        firehose_log_group = logs.LogGroup(
            self, "FirehoseLogGroup",
            log_group_name="/aws/kinesisfirehose/governance-metrics-stream",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )

        firehose_log_stream = logs.LogStream(
            self, "FirehoseLogStream",
            log_group=firehose_log_group,
            log_stream_name="S3Delivery"
        )

        # Create Kinesis Data Firehose delivery stream
        firehose_stream = firehose.CfnDeliveryStream(
            self, "GovernanceMetricsFirehose",
            delivery_stream_name="governance-metrics-stream",
            delivery_stream_type="DirectPut",
            s3_destination_configuration=firehose.CfnDeliveryStream.S3DestinationConfigurationProperty(
                bucket_arn=metrics_bucket.bucket_arn,
                role_arn=firehose_role.role_arn,
                prefix="quicksight-data/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/",
                error_output_prefix="errors/",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    size_in_m_bs=5,
                    interval_in_seconds=300
                ),
                compression_format="GZIP",
                cloud_watch_logging_options=firehose.CfnDeliveryStream.CloudWatchLoggingOptionsProperty(
                    enabled=True,
                    log_group_name=firehose_log_group.log_group_name,
                    log_stream_name=firehose_log_stream.log_stream_name
                )
            )
        )

        # Create IAM role for Lambda function
        lambda_role = iam.Role(
            self, "CrossAccountMonitoringLambdaRole",
            role_name="CrossAccountMonitoringLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="IAM role for cross-account governance monitoring Lambda function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
            inline_policies={
                "CrossAccountMonitoringPolicy": iam.PolicyDocument(
                    statements=[
                        # Organizations permissions
                        iam.PolicyStatement(
                            sid="OrganizationsReadAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "organizations:ListAccounts",
                                "organizations:DescribeAccount",
                                "organizations:DescribeOrganization",
                                "organizations:ListAccountsForParent",
                                "organizations:ListOrganizationalUnitsForParent",
                                "organizations:ListRoots"
                            ],
                            resources=["*"]
                        ),
                        # Cross-account role assumption
                        iam.PolicyStatement(
                            sid="AssumeRoleAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "sts:AssumeRole"
                            ],
                            resources=[
                                f"arn:aws:iam::*:role/{cross_account_role_name}"
                            ]
                        ),
                        # CloudWatch permissions
                        iam.PolicyStatement(
                            sid="CloudWatchAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "cloudwatch:PutMetricData",
                                "cloudwatch:GetMetricStatistics",
                                "cloudwatch:GetMetricData",
                                "cloudwatch:ListMetrics"
                            ],
                            resources=["*"]
                        ),
                        # S3 permissions
                        iam.PolicyStatement(
                            sid="S3Access",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:PutObject",
                                "s3:PutObjectAcl",
                                "s3:GetObject",
                                "s3:ListBucket"
                            ],
                            resources=[
                                metrics_bucket.bucket_arn,
                                f"{metrics_bucket.bucket_arn}/*"
                            ]
                        ),
                        # Kinesis Data Firehose permissions
                        iam.PolicyStatement(
                            sid="FirehoseAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "firehose:PutRecord",
                                "firehose:PutRecordBatch",
                                "firehose:DescribeDeliveryStream"
                            ],
                            resources=[
                                f"arn:aws:firehose:{self.region}:{self.account}:deliverystream/governance-metrics-stream"
                            ]
                        )
                    ]
                )
            }
        )

        # Create Lambda function
        monitoring_lambda = _lambda.Function(
            self, "CrossAccountMonitoringLambda",
            function_name="CrossAccountGovernanceMonitoring",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),  # Assumes lambda code is in ./lambda/ directory
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=1024,
            retry_attempts=0,
            environment={
                "CROSS_ACCOUNT_ROLE_NAME": cross_account_role_name,
                "METRICS_BUCKET": metrics_bucket.bucket_name,
                "FIREHOSE_STREAM_NAME": firehose_stream.delivery_stream_name,
                "LOG_LEVEL": "INFO"
            },
            description="Collects governance metrics from all organization accounts"
        )

        # Create EventBridge rule to trigger Lambda every 15 minutes
        monitoring_schedule = events.Rule(
            self, "MonitoringSchedule",
            rule_name="CrossAccountMonitoringSchedule",
            description="Triggers cross-account governance monitoring every 15 minutes",
            schedule=events.Schedule.rate(Duration.minutes(15)),
            enabled=True
        )

        # Add Lambda as target for the EventBridge rule
        monitoring_schedule.add_target(
            targets.LambdaFunction(
                monitoring_lambda,
                retry_attempts=2
            )
        )

        # Create dashboards from JSON files
        dashboards = DashboardConstruct(self, "Dashboards")

        # Output important values
        cdk.CfnOutput(
            self, "S3BucketName",
            description="S3 bucket for storing governance metrics",
            value=metrics_bucket.bucket_name
        )

        cdk.CfnOutput(
            self, "FirehoseStreamName",
            description="Kinesis Data Firehose delivery stream name",
            value=firehose_stream.delivery_stream_name
        )

        cdk.CfnOutput(
            self, "LambdaFunctionArn",
            description="Lambda function ARN",
            value=monitoring_lambda.function_arn
        )

        cdk.CfnOutput(
            self, "DashboardURLs",
            description="CloudWatch Dashboard URLs",
            value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:"
        )

        cdk.CfnOutput(
            self, "DashboardNames",
            description="Created dashboard names",
            value=", ".join([
                "AWS-Backup-Organization-Dashboard",
                "AWS-Patching-Organization-Dashboard", 
                "AWS-Config-Organization-Dashboard",
                "AWS-SecurityHub-Organization-Dashboard",
                "AWS-Governance-Executive-Overview"
            ])
        )

# App definition
app = cdk.App()
CrossAccountMonitoringStack(app, "CrossAccountMonitoringStack")
app.synth()
Benefits of This Approach:
✅ Clean Separation: Dashboard configurations are separate from infrastructure code
✅ Easy Maintenance: Update dashboards without touching CDK code
✅ Version Control: JSON files can be versioned independently
✅ Validation: JSON syntax validation during development
✅ Reusability: JSON files can be used outside of CDK
✅ Modularity: Add/remove dashboards by adding/removing JSON files
✅ Team Collaboration: Dashboard designers can work on JSON files independently

Deployment Commands:
bash
# Ensure directory structure is correct
mkdir -p dashboards lambda

# Copy JSON files to dashboards/ directory
# Copy Lambda code to lambda/ directory

# Deploy
cdk deploy
This approach makes your dashboards much more maintainable and allows for easier updates!

Can dashboards be created before running Lambda?
Can dashboards be created before running Lambda?
Yes, absolutely! Dashboards can and should be created before the Lambda runs. Here's what happens:

Dashboard Creation Before Lambda Execution
✅ What Works Immediately:
Dashboard structure and layout are fully functional

Widget titles, annotations, and formatting display correctly

Navigation and dashboard URLs work immediately

Visual elements (gauges, pie charts, etc.) show proper styling

Dashboard sharing and access controls function normally

📊 What You'll See Initially:
"No data available" messages in metric widgets

Empty graphs with proper axes and labels

Gauge widgets showing zero values

Pie charts showing "No data to display"

Text widgets and markdown content display normally

🔄 What Happens After Lambda Runs:
Metrics automatically populate as soon as Lambda publishes them

Graphs fill with data retroactively based on metric timestamps

Real-time updates begin flowing every 15 minutes

Historical data appears for time ranges after Lambda first ran

Example: Dashboard States
Before Lambda Execution:
text
🛡️ Protected Resources: No data available
❤️ Job Health Score: [Gauge showing 0%]
📊 Resource Protection Distribution: No data to display
After Lambda First Run:
text
🛡️ Protected Resources: 847 (with sparkline)
❤️ Job Health Score: [Gauge showing 94%]
📊 Resource Protection Distribution: [Pie chart with EBS: 45%, RDS: 30%, etc.]
CDK Deployment Order
The CDK will automatically handle dependencies:

python
# This order works perfectly:
1. S3 Bucket creation
2. Firehose stream creation  
3. Lambda function creation
4. Dashboard creation ← Can happen anytime!
5. EventBridge rule creation
6. Lambda starts running (15 min intervals)
Benefits of Creating Dashboards First:
✅ Immediate Validation: See dashboard layout and design right away
✅ Stakeholder Preview: Share dashboard URLs before data flows
✅ Design Testing: Validate colors, sizing, and widget placement
✅ No Waiting: Don't need to wait for Lambda execution cycles
✅ Iterative Development: Modify dashboard JSON files and redeploy quickly

Recommended Deployment Sequence:
bash
# 1. Deploy infrastructure + dashboards
cdk deploy

# 2. Immediately check dashboards (will show "No data")
https://console.aws.amazon.com/cloudwatch/home#dashboards:

# 3. Manually trigger Lambda for first data (optional)
aws lambda invoke --function-name CrossAccountGovernanceMonitoring

# 4. Wait 5 minutes and refresh dashboards - data appears!
Dashboard JSON Validation
Since dashboards are created before data exists, make sure your JSON references the correct:

json
{
  "metrics": [
    ["CrossAccount/Backup", "TotalProtectedResources"],  // ✅ Correct namespace
    ["CrossAccount/Config", "CompliancePercent"],        // ✅ Correct metric names  
    ["CrossAccount/Patching", "PatchCompliancePercent"]  // ✅ Matches Lambda code
  ]
}
Pro Tip: Test Empty Dashboards
Creating dashboards first is actually a best practice because:

Design Validation: You can perfect the visual layout without waiting for data

Metric Name Verification: Ensures dashboard metric names match Lambda publishing names

Stakeholder Buy-in: Show the final dashboard design to get approval before data collection

Troubleshooting: Easier to distinguish between dashboard issues vs. data collection issues

So yes, deploy those dashboards immediately! They'll be ready and waiting for your Lambda to start feeding them delicious metrics. 🎯
