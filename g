"""
CDK Stack for Cross-Account Governance Monitoring Infrastructure
==============================================================
Creates:
- S3 bucket for metrics storage
- Kinesis Data Firehose stream for QuickSight
- IAM roles for Firehose and Lambda
- Lambda function with proper permissions
"""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_kinesis as kinesis,
    aws_kinesisfirehose as firehose,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    Duration,
    RemovalPolicy
)
from constructs import Construct

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
            self, "FirehoseStreamArn",
            description="Kinesis Data Firehose delivery stream ARN",
            value=f"arn:aws:firehose:{self.region}:{self.account}:deliverystream/{firehose_stream.delivery_stream_name}"
        )

        cdk.CfnOutput(
            self, "LambdaFunctionArn",
            description="Lambda function ARN",
            value=monitoring_lambda.function_arn
        )

        cdk.CfnOutput(
            self, "LambdaRoleArn",
            description="Lambda execution role ARN",
            value=lambda_role.role_arn
        )

        cdk.CfnOutput(
            self, "CrossAccountRoleName",
            description="Name of the cross-account role to create in member accounts",
            value=cross_account_role_name
        )

        cdk.CfnOutput(
            self, "QuickSightS3DataSource",
            description="S3 path for QuickSight data source",
            value=f"s3://{metrics_bucket.bucket_name}/quicksight-data/"
        )


# App definition
app = cdk.App()
CrossAccountMonitoringStack(app, "CrossAccountMonitoringStack")
app.synth()
