# The Iceberg catalogue: a Glue database. pyiceberg (LAKEHOUSE_CATALOG=glue) creates and commits the tables;
# Athena reads the published (main) branch.
resource "aws_glue_catalog_database" "macro" {
  name        = "macro"
  description = "UK official statistics and market data, every vintage, Iceberg tables."
}

resource "aws_athena_workgroup" "analysts" {
  name          = "${var.project}-analysts"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 10737418240 # 10 GB: a runaway query can't run up the bill

    result_configuration {
      output_location = "s3://${aws_s3_bucket.lake.bucket}/athena/"
      encryption_configuration {
        encryption_option = "SSE_KMS"
      }
    }

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }
  }
}
