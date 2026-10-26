data "aws_caller_identity" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  glue_arns = [
    "arn:aws:glue:${var.region}:${local.account}:catalog",
    "arn:aws:glue:${var.region}:${local.account}:database/${aws_glue_catalog_database.macro.name}",
    "arn:aws:glue:${var.region}:${local.account}:table/${aws_glue_catalog_database.macro.name}/*",
  ]
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Pulls the image and writes logs; nothing else.
resource "aws_iam_role" "execution" {
  name_prefix        = "${var.project}-exec-"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# What the pipeline itself may do: read and write this bucket, and manage tables in the macro database only.
resource "aws_iam_role" "task" {
  name_prefix        = "${var.project}-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "ListLake"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.lake.arn]
  }
  statement {
    sid       = "ReadWriteLake"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*", "${aws_s3_bucket.lake.arn}/warehouse/*"]
  }
  statement {
    sid = "IcebergCatalog"
    actions = [
      "glue:GetDatabase", "glue:CreateDatabase", "glue:GetTable", "glue:GetTables", "glue:CreateTable", "glue:UpdateTable",
      "glue:GetPartitions",
    ]
    resources = local.glue_arns
  }
  statement {
    sid       = "EncryptedObjects"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# EventBridge Scheduler may start exactly this task and hand it its two roles.
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name_prefix        = "${var.project}-sched-"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.pull.arn_without_revision, "${aws_ecs_task_definition.pull.arn_without_revision}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.pipeline.arn]
    }
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.task.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
