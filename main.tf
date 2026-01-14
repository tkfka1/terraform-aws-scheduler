locals {
  assume_role_arns = [
    for account in var.accounts : (
      startswith(account.iam_role, "arn:")
      ? account.iam_role
      : "arn:aws:iam::${account.account_id}:role/${account.iam_role}"
    )
  ]
  eventbridge_log_group_name = trimspace(var.eventbridge_log_group_name) != "" ? trimspace(var.eventbridge_log_group_name) : "/aws/events/${var.event_rule_name}"
  verification_table_name    = trimspace(var.verification_table_name) != "" ? trimspace(var.verification_table_name) : "${var.lambda_function_name}-verification"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/scheduler-lambda.zip"
}

resource "aws_iam_role" "lambda" {
  name               = var.lambda_role_name
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.lambda_role_name}-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_policy.json
}

data "aws_iam_policy_document" "lambda_policy" {
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    actions   = ["sts:AssumeRole"]
    resources = local.assume_role_arns
  }

  dynamic "statement" {
    for_each = var.enable_rds ? [1] : []
    content {
      actions = [
        "rds:DescribeDBInstances",
        "rds:DescribeDBClusters",
        "rds:ListTagsForResource",
        "rds:StartDBInstance",
        "rds:StopDBInstance",
        "rds:StartDBCluster",
        "rds:StopDBCluster",
      ]
      resources = ["*"]
    }
  }

  dynamic "statement" {
    for_each = var.enable_verification ? [1] : []
    content {
      actions = [
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
      ]
      resources = [aws_dynamodb_table.verification[0].arn]
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}

resource "aws_lambda_function" "scheduler" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda.arn
  handler       = "lambda_function.handler"
  runtime       = "python3.11"
  filename      = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout_seconds

  environment {
    variables = {
      ACCOUNTS_JSON      = jsonencode(var.accounts)
      LOG_LEVEL          = var.log_level
      TIMEZONE           = var.timezone
      ENABLE_EC2         = tostring(var.enable_ec2)
      ENABLE_RDS         = tostring(var.enable_rds)
      ENABLE_ASG         = tostring(var.enable_asg)
      TAG_SCHEDULE_KEY   = var.tag_schedule_key
      TAG_SCHEDULE_VALUE = var.tag_schedule_value
      TAG_START_KEY      = var.tag_start_key
      TAG_STOP_KEY       = var.tag_stop_key
      TAG_WEEKDAY_KEY    = var.tag_weekday_key
      TAG_ASG_MIN_KEY    = var.tag_asg_min_key
      TAG_ASG_MAX_KEY    = var.tag_asg_max_key
      TAG_ASG_DESIRED_KEY = var.tag_asg_desired_key
      NOTIFICATION_TAG_KEYS = jsonencode(var.notification_tag_keys)
      ENABLE_VERIFICATION = tostring(var.enable_verification)
      VERIFICATION_DELAY_MINUTES = tostring(var.verification_delay_minutes)
      VERIFICATION_TABLE_NAME = local.verification_table_name
      VERIFICATION_TTL_DAYS = tostring(var.verification_ttl_days)
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "hourly" {
  name                = var.event_rule_name
  schedule_expression = var.schedule_expression
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.hourly.name
  target_id = "scheduler"
  arn       = aws_lambda_function.scheduler.arn
}

resource "aws_dynamodb_table" "verification" {
  count = var.enable_verification ? 1 : 0

  name         = local.verification_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "eventbridge" {
  count = var.enable_eventbridge_logging ? 1 : 0

  name              = local.eventbridge_log_group_name
  retention_in_days = var.eventbridge_log_retention_in_days
  tags              = var.tags
}

data "aws_iam_policy_document" "eventbridge_logs" {
  count = var.enable_eventbridge_logging ? 1 : 0

  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    resources = ["${aws_cloudwatch_log_group.eventbridge[0].arn}:*"]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.hourly.arn]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "eventbridge" {
  count = var.enable_eventbridge_logging ? 1 : 0

  policy_name     = "${var.event_rule_name}-eventbridge-logs"
  policy_document = data.aws_iam_policy_document.eventbridge_logs[0].json
}

resource "aws_cloudwatch_event_target" "logs" {
  count = var.enable_eventbridge_logging ? 1 : 0

  rule      = aws_cloudwatch_event_rule.hourly.name
  target_id = "eventbridge-logs"
  arn       = aws_cloudwatch_log_group.eventbridge[0].arn

  depends_on = [aws_cloudwatch_log_resource_policy.eventbridge]
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly.arn
}
