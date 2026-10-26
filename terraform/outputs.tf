output "lake_bucket" {
  description = "Bucket holding raw/ downloads, warehouse/ Iceberg tables and athena/ results."
  value       = aws_s3_bucket.lake.bucket
}

output "iceberg_warehouse" {
  description = "Set as LAKEHOUSE_WAREHOUSE for pyiceberg."
  value       = "s3://${aws_s3_bucket.lake.bucket}/warehouse"
}

output "glue_database" {
  value = aws_glue_catalog_database.macro.name
}

output "athena_workgroup" {
  value = aws_athena_workgroup.analysts.name
}

output "ecr_repository_url" {
  description = "Push the pipeline image here."
  value       = aws_ecr_repository.pipeline.repository_url
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
