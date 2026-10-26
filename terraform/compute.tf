# The scheduled pull: a Fargate task (image built from ../Dockerfile) that restores the raw cache from S3, runs
# `make pull` against the Glue catalogue (write-audit-publish into S3 Iceberg tables) and saves new raw files back.
resource "aws_ecr_repository" "pipeline" {
  name                 = var.project
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecs_cluster" "pipeline" {
  name = var.project
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/ecs/${var.project}"
  retention_in_days = 90
}

resource "aws_ecs_task_definition" "pull" {
  family                   = "${var.project}-pull"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 4096
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "pull"
    image     = "${aws_ecr_repository.pipeline.repository_url}:${var.image_tag}"
    essential = true
    command = ["sh", "-c", join(" && ", [
      "aws s3 sync s3://${aws_s3_bucket.lake.bucket}/raw data/raw",
      "make pull",
      "aws s3 sync data/raw s3://${aws_s3_bucket.lake.bucket}/raw",
    ])]
    environment = [
      { name = "LAKEHOUSE_CATALOG", value = "glue" },
      { name = "LAKEHOUSE_WAREHOUSE", value = "s3://${aws_s3_bucket.lake.bucket}/warehouse" },
      { name = "AWS_REGION", value = var.region },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.pipeline.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "pull"
      }
    }
  }])
}

resource "aws_scheduler_schedule" "daily_pull" {
  name                         = "${var.project}-daily-pull"
  schedule_expression          = var.schedule
  schedule_expression_timezone = "Europe/London"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.pipeline.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.pull.arn
      launch_type         = "FARGATE"
      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = var.security_group_ids
        assign_public_ip = false
      }
    }

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}

# A run that exits non-zero (a NEW vintage failed its audit, or the pipeline broke) alerts the team.
resource "aws_sns_topic" "alerts" {
  name              = "${var.project}-alerts"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_event_rule" "pull_failed" {
  name        = "${var.project}-pull-failed"
  description = "The scheduled pull task stopped with a non-zero exit code."
  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn        = [aws_ecs_cluster.pipeline.arn]
      lastStatus        = ["STOPPED"]
      containers        = { exitCode = [{ "anything-but" = 0 }] }
      taskDefinitionArn = [{ prefix = "arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.project}-pull" }]
    }
  })
}

resource "aws_cloudwatch_event_target" "pull_failed" {
  rule = aws_cloudwatch_event_rule.pull_failed.name
  arn  = aws_sns_topic.alerts.arn
}

resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.alerts.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.pull_failed.arn } }
    }]
  })
}
