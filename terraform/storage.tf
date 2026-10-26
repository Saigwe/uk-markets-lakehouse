# One bucket: raw/ is the immutable landing zone (every downloaded release), warehouse/ holds the Iceberg tables,
# athena/ holds query results. Versioned, encrypted, never public.
resource "aws_s3_bucket" "lake" {
  bucket_prefix = "${var.project}-"
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    id     = "raw-downloads"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    expiration {
      days = var.raw_retention_days
    }
  }

  rule {
    id     = "athena-results"
    status = "Enabled"
    filter {
      prefix = "athena/"
    }
    expiration {
      days = 30
    }
  }

  rule {
    id     = "old-object-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}
