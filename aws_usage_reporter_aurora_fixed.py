#!/usr/bin/env python3
"""
AWS Usage Report Generator - Aurora Fixed
Added Aurora engine types to RDS classification

Aurora engines now included in RDS:
- aurora (original Aurora MySQL-compatible)
- aurora-mysql (Aurora MySQL-compatible)  
- aurora-postgresql (Aurora PostgreSQL-compatible)

Version: 4.2 - Aurora Classification Fixed
Author: AWS DevOps Engineer
Date: October 2025
"""

import boto3
import json
import csv
import time
import sys
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
from typing import Dict, List, Any
import warnings
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger(__name__)

class AWSUsageReporter:
    """AWS Usage Reporter with Aurora properly classified under RDS"""

    def __init__(self, region: str = 'us-east-1', max_retries: int = 3):
        self.region = region
        self.max_retries = max_retries
        self.report_data = []
        self.logger = logging.getLogger(__name__)

        # AWS Engine type definitions - AURORA ADDED TO RDS
        self.RDS_ENGINES = [
            # Traditional RDS engines
            'mysql', 'postgres', 'oracle-ee', 'oracle-se2', 'oracle-se1', 'oracle-se',
            'sqlserver-ee', 'sqlserver-se', 'sqlserver-ex', 'sqlserver-web', 'mariadb',
            # Aurora engines (part of RDS family)
            'aurora', 'aurora-mysql', 'aurora-postgresql'
        ]
        self.NEPTUNE_ENGINES = ['neptune']
        self.DOCUMENTDB_ENGINES = ['docdb']

        self._initialize_clients()
        self.logger.info(f"✅ AWS Usage Reporter initialized for region: {region}")
        self.logger.info("🔧 Aurora engines now included in RDS classification")

    def _initialize_clients(self):
        """Initialize AWS service clients"""
        config = Config(
            retries={'max_attempts': self.max_retries, 'mode': 'adaptive'},
            max_pool_connections=50,
            region_name=self.region
        )

        self.ec2_client = boto3.client('ec2', config=config)
        self.lambda_client = boto3.client('lambda', config=config)
        self.eks_client = boto3.client('eks', config=config)
        self.glue_client = boto3.client('glue', config=config)
        self.s3_client = boto3.client('s3', config=config)
        self.efs_client = boto3.client('efs', config=config)
        self.fsx_client = boto3.client('fsx', config=config)
        self.storagegateway_client = boto3.client('storagegateway', config=config)
        self.docdb_client = boto3.client('docdb', config=config)
        self.rds_client = boto3.client('rds', config=config)
        self.neptune_client = boto3.client('neptune', config=config)
        self.dynamodb_client = boto3.client('dynamodb', config=config)
        self.redshift_client = boto3.client('redshift', config=config)
        self.cloudwatch_client = boto3.client('cloudwatch', config=config)

    def _paginate_all(self, client, operation_name: str, result_key: str, **kwargs):
        """Paginate and return all results"""
        try:
            if hasattr(client, 'get_paginator'):
                paginator = client.get_paginator(operation_name)
                results = []
                for page in paginator.paginate(**kwargs):
                    if result_key in page:
                        data = page[result_key]
                        results.extend(data if isinstance(data, list) else [data])
                return results
            else:
                response = getattr(client, operation_name)(**kwargs)
                return response.get(result_key, [])
        except Exception as e:
            self.logger.warning(f"Failed to paginate {operation_name}: {e}")
            return []

    def get_ec2_ebs_metrics(self) -> Dict[str, Any]:
        """EC2/EBS: Instance Count + In-Use Capacity (EBS Storage)"""
        try:
            self.logger.info("📊 Collecting EC2/EBS essentials...")

            reservations = self._paginate_all(self.ec2_client, 'describe_instances', 'Reservations')
            running_instances = 0
            for reservation in reservations:
                for instance in reservation.get('Instances', []):
                    if instance.get('State', {}).get('Name') == 'running':
                        running_instances += 1

            volumes = self._paginate_all(self.ec2_client, 'describe_volumes', 'Volumes')
            total_ebs_storage = sum(vol.get('Size', 0) for vol in volumes if vol.get('State') == 'in-use')

            return {
                'Service': 'EC2/EBS',
                'Instance_Count': running_instances,
                'In_Use_Capacity_GB': total_ebs_storage,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"EC2/EBS failed: {e}")
            return {'Service': 'EC2/EBS', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_lambda_metrics(self) -> Dict[str, Any]:
        """Lambda: Function Count + In-Use Capacity (Total Memory)"""
        try:
            self.logger.info("📊 Collecting Lambda essentials...")

            functions = self._paginate_all(self.lambda_client, 'list_functions', 'Functions')
            function_count = len(functions)
            total_memory = sum(f.get('MemorySize', 0) for f in functions)

            return {
                'Service': 'Lambda',
                'Instance_Count': function_count,
                'In_Use_Capacity_MB': total_memory,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"Lambda failed: {e}")
            return {'Service': 'Lambda', 'Instance_Count': 0, 'In_Use_Capacity_MB': 0, 'Region': self.region, 'Error': str(e)}

    def get_eks_metrics(self) -> Dict[str, Any]:
        """EKS: Cluster Count + In-Use Capacity (Total Nodes)"""
        try:
            self.logger.info("📊 Collecting EKS essentials...")

            clusters = self.eks_client.list_clusters().get('clusters', [])
            cluster_count = len(clusters)
            total_nodes = 0

            for cluster_name in clusters:
                try:
                    nodegroups = self.eks_client.list_nodegroups(clusterName=cluster_name).get('nodegroups', [])
                    for ng_name in nodegroups:
                        ng_info = self.eks_client.describe_nodegroup(clusterName=cluster_name, nodegroupName=ng_name)
                        total_nodes += ng_info['nodegroup']['scalingConfig'].get('desiredSize', 0)
                except Exception:
                    continue

            return {
                'Service': 'EKS',
                'Instance_Count': cluster_count,
                'In_Use_Capacity_Nodes': total_nodes,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"EKS failed: {e}")
            return {'Service': 'EKS', 'Instance_Count': 0, 'In_Use_Capacity_Nodes': 0, 'Region': self.region, 'Error': str(e)}

    def get_glue_metrics(self) -> Dict[str, Any]:
        """Glue: Job Count + In-Use Capacity (Total DPU)"""
        try:
            self.logger.info("📊 Collecting Glue essentials...")

            jobs = self._paginate_all(self.glue_client, 'get_jobs', 'Jobs')
            job_count = len(jobs)

            total_dpu = 0
            for job in jobs:
                if 'MaxCapacity' in job:
                    total_dpu += job['MaxCapacity']
                elif 'NumberOfWorkers' in job:
                    worker_type = job.get('WorkerType', 'Standard')
                    multiplier = {'G.025X': 0.25, 'G.1X': 1, 'G.2X': 2, 'G.4X': 4, 'G.8X': 8}.get(worker_type, 2)
                    total_dpu += job['NumberOfWorkers'] * multiplier

            return {
                'Service': 'Glue',
                'Instance_Count': job_count,
                'In_Use_Capacity_DPU': round(total_dpu, 2),
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"Glue failed: {e}")
            return {'Service': 'Glue', 'Instance_Count': 0, 'In_Use_Capacity_DPU': 0, 'Region': self.region, 'Error': str(e)}

    def _get_bucket_metrics_parallel(self, bucket_name: str) -> Dict[str, Any]:
        """Get metrics for a single bucket using CloudWatch"""
        try:
            end_time = datetime.now()
            size_gb = 0
            object_count = 0

            for days_back in [1, 2, 7]:
                try:
                    period_start = end_time - timedelta(days=days_back)
                    size_response = self.cloudwatch_client.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='BucketSizeBytes',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'StandardStorage'}
                        ],
                        StartTime=period_start,
                        EndTime=end_time,
                        Period=86400,
                        Statistics=['Average']
                    )

                    if size_response.get('Datapoints'):
                        latest_size = max(size_response['Datapoints'], key=lambda x: x['Timestamp'])['Average']
                        size_gb = latest_size / (1024**3)
                        break
                except Exception:
                    continue

            for days_back in [1, 2, 7]:
                try:
                    period_start = end_time - timedelta(days=days_back)
                    count_response = self.cloudwatch_client.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='NumberOfObjects',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'AllStorageTypes'}
                        ],
                        StartTime=period_start,
                        EndTime=end_time,
                        Period=86400,
                        Statistics=['Average']
                    )

                    if count_response.get('Datapoints'):
                        latest_count = max(count_response['Datapoints'], key=lambda x: x['Timestamp'])['Average']
                        object_count = int(latest_count)
                        break
                except Exception:
                    continue

            return {
                'bucket': bucket_name,
                'size_gb': size_gb,
                'objects': object_count,
                'has_data': size_gb > 0 or object_count > 0
            }

        except Exception as e:
            self.logger.debug(f"Failed to get metrics for {bucket_name}: {e}")
            return {'bucket': bucket_name, 'size_gb': 0, 'objects': 0, 'has_data': False}

    def get_s3_metrics(self) -> Dict[str, Any]:
        """S3: Bucket Count + In-Use Capacity (Storage) + Object Count (IMPROVED)"""
        try:
            self.logger.info("📊 Collecting S3 essentials (improved processing)...")

            buckets = self.s3_client.list_buckets().get('Buckets', [])
            bucket_count = len(buckets)

            self.logger.info(f"Processing {bucket_count} S3 buckets...")

            total_size_gb = 0
            total_objects = 0
            processed_buckets = 0

            max_workers = min(20, bucket_count)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_bucket = {
                    executor.submit(self._get_bucket_metrics_parallel, bucket['Name']): bucket['Name'] 
                    for bucket in buckets
                }

                for future in as_completed(future_to_bucket, timeout=300):
                    try:
                        result = future.result(timeout=30)
                        if result['has_data']:
                            total_size_gb += result['size_gb']
                            total_objects += result['objects']
                            processed_buckets += 1

                        if processed_buckets % 10 == 0:
                            self.logger.info(f"Processed {processed_buckets} buckets with data...")

                    except Exception as e:
                        bucket_name = future_to_bucket[future]
                        self.logger.debug(f"Bucket {bucket_name} processing failed: {e}")

            self.logger.info(f"S3 processing complete: {processed_buckets}/{bucket_count} buckets had data")

            return {
                'Service': 'S3',
                'Instance_Count': bucket_count,
                'In_Use_Capacity_GB': round(total_size_gb, 2),
                'Object_Count': total_objects,
                'Processed_Buckets': processed_buckets,
                'Region': 'global'
            }

        except Exception as e:
            self.logger.error(f"S3 failed: {e}")
            return {'Service': 'S3', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Object_Count': 0, 'Region': 'global', 'Error': str(e)}

    def get_efs_metrics(self) -> Dict[str, Any]:
        """EFS: File System Count + In-Use Capacity (Storage)"""
        try:
            self.logger.info("📊 Collecting EFS essentials...")

            file_systems = self._paginate_all(self.efs_client, 'describe_file_systems', 'FileSystems')
            fs_count = len(file_systems)
            total_storage = sum(fs.get('SizeInBytes', {}).get('Value', 0) for fs in file_systems) / (1024**3)

            return {
                'Service': 'EFS',
                'Instance_Count': fs_count,
                'In_Use_Capacity_GB': round(total_storage, 2),
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"EFS failed: {e}")
            return {'Service': 'EFS', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_fsx_metrics(self) -> Dict[str, Any]:
        """FSx: File System Count + In-Use Capacity (Storage)"""
        try:
            self.logger.info("📊 Collecting FSx essentials...")

            file_systems = self._paginate_all(self.fsx_client, 'describe_file_systems', 'FileSystems')
            fs_count = len(file_systems)
            total_capacity = sum(fs.get('StorageCapacity', 0) for fs in file_systems)

            return {
                'Service': 'FSx',
                'Instance_Count': fs_count,
                'In_Use_Capacity_GB': total_capacity,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"FSx failed: {e}")
            return {'Service': 'FSx', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_storage_gateway_metrics(self) -> Dict[str, Any]:
        """Storage Gateway: Gateway Count + In-Use Capacity"""
        try:
            self.logger.info("📊 Collecting Storage Gateway essentials...")

            gateways = self.storagegateway_client.list_gateways().get('Gateways', [])
            gateway_count = len(gateways)

            return {
                'Service': 'Storage Gateway',
                'Instance_Count': gateway_count,
                'In_Use_Capacity_GB': 0,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"Storage Gateway failed: {e}")
            return {'Service': 'Storage Gateway', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_documentdb_metrics(self) -> Dict[str, Any]:
        """DocumentDB: Instance Count + In-Use Capacity - ENGINE FILTERED"""
        try:
            self.logger.info("📊 Collecting DocumentDB essentials (engine-filtered)...")

            all_instances = self._paginate_all(self.docdb_client, 'describe_db_instances', 'DBInstances')

            documentdb_instances = [
                instance for instance in all_instances 
                if instance.get('Engine', '').lower() in self.DOCUMENTDB_ENGINES
            ]

            instance_count = len(documentdb_instances)

            total_storage = 0
            try:
                clusters = self._paginate_all(self.docdb_client, 'describe_db_clusters', 'DBClusters')
                docdb_clusters = [
                    cluster for cluster in clusters
                    if cluster.get('Engine', '').lower() in self.DOCUMENTDB_ENGINES
                ]
                total_storage = len(docdb_clusters) * 10
            except Exception as storage_error:
                self.logger.debug(f"Could not calculate DocumentDB storage: {storage_error}")

            self.logger.info(f"   DocumentDB: {instance_count} instances (docdb engine only)")

            return {
                'Service': 'DocumentDB',
                'Instance_Count': instance_count,
                'In_Use_Capacity_GB': total_storage,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"DocumentDB failed: {e}")
            return {'Service': 'DocumentDB', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_rds_metrics(self) -> Dict[str, Any]:
        """RDS: Instance Count + In-Use Capacity - NOW INCLUDES AURORA"""
        try:
            self.logger.info("📊 Collecting RDS essentials (includes Aurora)...")

            all_instances = self._paginate_all(self.rds_client, 'describe_db_instances', 'DBInstances')

            # Filter for RDS engines (now includes Aurora)
            rds_instances = [
                instance for instance in all_instances 
                if instance.get('Engine', '').lower() in self.RDS_ENGINES
            ]

            instance_count = len(rds_instances)
            total_storage = sum(inst.get('AllocatedStorage', 0) for inst in rds_instances)

            # Count Aurora vs traditional instances for logging
            aurora_instances = [inst for inst in rds_instances if 'aurora' in inst.get('Engine', '').lower()]
            traditional_instances = [inst for inst in rds_instances if 'aurora' not in inst.get('Engine', '').lower()]

            self.logger.info(f"   RDS: {instance_count} total instances")
            self.logger.info(f"     - Traditional RDS: {len(traditional_instances)} instances")
            self.logger.info(f"     - Aurora: {len(aurora_instances)} instances")

            engines_found = set(inst.get('Engine', 'unknown').lower() for inst in rds_instances)
            self.logger.debug(f"   RDS engines found: {engines_found}")

            return {
                'Service': 'RDS',
                'Instance_Count': instance_count,
                'In_Use_Capacity_GB': total_storage,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"RDS failed: {e}")
            return {'Service': 'RDS', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_neptune_metrics(self) -> Dict[str, Any]:
        """Neptune: Instance Count + In-Use Capacity - ENGINE FILTERED"""
        try:
            self.logger.info("📊 Collecting Neptune essentials (engine-filtered)...")

            all_instances = self._paginate_all(self.neptune_client, 'describe_db_instances', 'DBInstances')

            neptune_instances = [
                instance for instance in all_instances 
                if instance.get('Engine', '').lower() in self.NEPTUNE_ENGINES
            ]

            instance_count = len(neptune_instances)

            total_storage = 0
            try:
                clusters = self._paginate_all(self.neptune_client, 'describe_db_clusters', 'DBClusters')
                neptune_clusters = [
                    cluster for cluster in clusters
                    if cluster.get('Engine', '').lower() in self.NEPTUNE_ENGINES
                ]
                total_storage = len(neptune_clusters) * 10
            except Exception as storage_error:
                self.logger.debug(f"Could not calculate Neptune storage: {storage_error}")

            self.logger.info(f"   Neptune: {instance_count} instances (neptune engine only)")

            return {
                'Service': 'Neptune',
                'Instance_Count': instance_count,
                'In_Use_Capacity_GB': total_storage,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"Neptune failed: {e}")
            return {'Service': 'Neptune', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_dynamodb_metrics(self) -> Dict[str, Any]:
        """DynamoDB: Table Count + In-Use Capacity (Storage Size)"""
        try:
            self.logger.info("📊 Collecting DynamoDB essentials...")

            tables = self._paginate_all(self.dynamodb_client, 'list_tables', 'TableNames')
            table_count = len(tables)

            total_size = 0
            sample_size = min(20, table_count)

            for table_name in tables[:sample_size]:
                try:
                    table_info = self.dynamodb_client.describe_table(TableName=table_name)
                    size_bytes = table_info['Table'].get('TableSizeBytes', 0)
                    total_size += size_bytes
                except Exception:
                    continue

            if sample_size > 0:
                avg_size = total_size / sample_size
                estimated_total = (avg_size * table_count) / (1024**3)
            else:
                estimated_total = 0

            return {
                'Service': 'DynamoDB',
                'Instance_Count': table_count,
                'In_Use_Capacity_GB': round(estimated_total, 2),
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"DynamoDB failed: {e}")
            return {'Service': 'DynamoDB', 'Instance_Count': 0, 'In_Use_Capacity_GB': 0, 'Region': self.region, 'Error': str(e)}

    def get_redshift_metrics(self) -> Dict[str, Any]:
        """Redshift: Cluster Count + In-Use Capacity (Total Nodes)"""
        try:
            self.logger.info("📊 Collecting Redshift essentials...")

            clusters = self._paginate_all(self.redshift_client, 'describe_clusters', 'Clusters')
            cluster_count = len(clusters)
            total_nodes = sum(cluster.get('NumberOfNodes', 1) for cluster in clusters)

            return {
                'Service': 'Redshift',
                'Instance_Count': cluster_count,
                'In_Use_Capacity_Nodes': total_nodes,
                'Region': self.region
            }
        except Exception as e:
            self.logger.error(f"Redshift failed: {e}")
            return {'Service': 'Redshift', 'Instance_Count': 0, 'In_Use_Capacity_Nodes': 0, 'Region': self.region, 'Error': str(e)}

    def generate_report(self) -> List[Dict[str, Any]]:
        """Generate report with Aurora properly included in RDS"""
        self.logger.info("🚀 Starting AWS Usage Report - Aurora Fixed")
        self.logger.info("=" * 70)

        service_methods = [
            self.get_ec2_ebs_metrics,
            self.get_lambda_metrics,
            self.get_eks_metrics,
            self.get_glue_metrics,
            self.get_s3_metrics,
            self.get_efs_metrics,
            self.get_fsx_metrics,
            self.get_storage_gateway_metrics,
            self.get_documentdb_metrics,
            self.get_rds_metrics,         # Now includes Aurora
            self.get_neptune_metrics,
            self.get_dynamodb_metrics,
            self.get_redshift_metrics,
        ]

        self.report_data = []

        for i, method in enumerate(service_methods, 1):
            service_name = method.__name__.replace('get_', '').replace('_metrics', '').upper()
            try:
                self.logger.info(f"[{i}/{len(service_methods)}] {service_name}...")
                result = method()
                self.report_data.append(result)

                if 'Error' not in result:
                    instance_count = result.get('Instance_Count', 0)
                    capacity = result.get('In_Use_Capacity_GB', result.get('In_Use_Capacity_MB', result.get('In_Use_Capacity_DPU', result.get('In_Use_Capacity_Nodes', 0))))
                    self.logger.info(f"   ✅ {service_name}: {instance_count} instances, {capacity} capacity")
                else:
                    self.logger.warning(f"   ❌ {service_name}: {result['Error']}")

                time.sleep(0.3)

            except Exception as e:
                self.logger.error(f"❌ {service_name} failed: {e}")
                self.report_data.append({
                    'Service': service_name,
                    'Instance_Count': 0,
                    'In_Use_Capacity_GB': 0,
                    'Region': self.region,
                    'Error': str(e)
                })

        return self.report_data

    def save_to_csv(self, filename: str = None) -> str:
        """Save report with Aurora fixed to CSV"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"aws_usage_aurora_fixed_{self.region}_{timestamp}.csv"

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Service', 'Region', 'Instance_Count', 'In_Use_Capacity_GB', 'Object_Count', 'Error']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()

                for record in self.report_data:
                    clean_record = {
                        'Service': record.get('Service', ''),
                        'Region': record.get('Region', ''),
                        'Instance_Count': record.get('Instance_Count', 0),
                        'In_Use_Capacity_GB': record.get('In_Use_Capacity_GB', 
                                                       record.get('In_Use_Capacity_MB', 
                                                                record.get('In_Use_Capacity_DPU', 
                                                                         record.get('In_Use_Capacity_Nodes', 0)))),
                        'Object_Count': record.get('Object_Count', ''),
                        'Error': record.get('Error', '')
                    }
                    writer.writerow(clean_record)

            self.logger.info(f"✅ Aurora-fixed report saved: {filename}")
            return filename

        except Exception as e:
            self.logger.error(f"❌ CSV save failed: {e}")
            raise

    def print_summary(self):
        """Print summary with Aurora classification"""
        print("\n" + "=" * 90)
        print("📋 AWS USAGE REPORT - AURORA CLASSIFICATION FIXED")
        print("=" * 90)
        print(f"Region: {self.region}")
        print("\nDatabase Service Classification:")
        print("  • RDS: Traditional databases + Aurora (MySQL/PostgreSQL)")
        print("  • Neptune: Graph database (neptune engine)")
        print("  • DocumentDB: MongoDB-compatible (docdb engine)")
        print("\nAurora engines now included in RDS:")
        print("  • aurora, aurora-mysql, aurora-postgresql")
        print("\n" + "-" * 90)
        print(f"{'Service':<20} {'Instances':<12} {'Capacity':<15} {'Objects':<12} {'Status'}")
        print("-" * 90)

        for record in self.report_data:
            service = record.get('Service', '')[:19]
            instances = record.get('Instance_Count', 0)

            capacity = record.get('In_Use_Capacity_GB', 0)
            capacity_unit = 'GB'

            if capacity == 0:
                capacity = record.get('In_Use_Capacity_MB', 0)
                capacity_unit = 'MB'
            if capacity == 0:
                capacity = record.get('In_Use_Capacity_DPU', 0)
                capacity_unit = 'DPU'
            if capacity == 0:
                capacity = record.get('In_Use_Capacity_Nodes', 0)
                capacity_unit = 'Nodes'

            capacity_str = f"{capacity} {capacity_unit}" if capacity > 0 else "0"
            objects = record.get('Object_Count', '')
            objects_str = f"{objects:,}" if objects else ""
            status = "✅" if 'Error' not in record else "❌"

            print(f"{service:<20} {instances:<12} {capacity_str:<15} {objects_str:<12} {status}")

def main():
    """Main function - Aurora classification fixed"""
    import argparse

    parser = argparse.ArgumentParser(description='AWS Usage Report - Aurora Classification Fixed')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--output-csv', help='Output CSV filename')
    parser.add_argument('--print-summary', action='store_true', help='Print summary')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    logger = setup_logging(args.verbose)

    try:
        logger.info("🚀 AWS Usage Reporter - Aurora Classification Fixed")
        logger.info("🔧 Aurora engines now properly included in RDS")

        reporter = AWSUsageReporter(region=args.region)

        start_time = time.time()
        report_data = reporter.generate_report()
        end_time = time.time()

        logger.info(f"\nReport completed in {end_time - start_time:.1f} seconds")

        csv_file = reporter.save_to_csv(args.output_csv)

        if args.print_summary or not args.output_csv:
            reporter.print_summary()

        logger.info(f"\n✅ Aurora classification fixed report complete: {csv_file}")
        return 0

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
