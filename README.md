# terraform-aws-scheduler

EC2, RDS, and Auto Scaling Group scheduler module built with Lambda + EventBridge.
The Lambda runs on an EventBridge schedule and starts, stops, or scales resources based on tag-defined time windows in a configurable timezone.

Repository: https://github.com/tkfka1/terraform-aws-scheduler

## What It Does

- Runs on an EventBridge `rate(...)` or `cron(...)` schedule
- Evaluates resource tags in a configurable timezone, default `Asia/Seoul`
- Supports EC2, RDS DB instances, RDS clusters, and Auto Scaling Groups
- Uses cross-account `AssumeRole` for target accounts
- Sends optional Teams, Slack, or Telegram notifications
- Supports optional delayed verification with DynamoDB
- Avoids duplicate actions when a resource is already in the desired state

## Quick Start

1. Deploy the module in the scheduler account.
2. Add the scheduler trust policy to the target account role.
3. Tag target resources with `Schedule = True` and `Schedule_Windows = ...`.
4. Wait for the EventBridge rule to invoke the Lambda on the next tick.

## Schedule Tag Model

The scheduler uses two tags for normal resources:

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 18:00
```

Rules:

- `Schedule` must match the configured enable tag key/value.
- `Schedule_Windows` is required. Missing or invalid values are ignored.
- Each window entry is `StartDay StartTime EndDay EndTime`.
- Multiple windows are separated by `;` or line breaks.
- Day names: recommended `Mon Tue Wed Thu Fri Sat Sun`. Full names like `Monday` are also accepted.
- Time format: `HH` or `HH:MM`.
- Start is inclusive, end is exclusive.
- Always write the real end day. For Friday 07:00 to Saturday 01:00, write `Fri 07:00 Sat 01:00`.
- `timezone` controls schedule evaluation. It does not depend on the Lambda host timezone.

Recommended custom key variables:

- `tag_schedule_key`
- `tag_schedule_value`
- `tag_window_key`

## Schedule_Windows Examples

Same-day window:

```text
Schedule = True
Schedule_Windows = Mon 10:00 Mon 12:00
```

Overnight window:

```text
Schedule = True
Schedule_Windows = Mon 22:00 Tue 02:00
```

Friday morning to Saturday early morning:

```text
Schedule = True
Schedule_Windows = Fri 07:00 Sat 01:00
```

Multiple windows on the same day:

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 12:00; Mon 13:00 Mon 18:00
```

Business week:

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 18:00; Tue 09:00 Tue 18:00; Wed 09:00 Wed 18:00; Thu 09:00 Thu 18:00; Fri 09:00 Fri 18:00
```

Weekend only:

```text
Schedule = True
Schedule_Windows = Sat 10:00 Sat 16:00; Sun 10:00 Sun 16:00
```

## Resource Tag Examples

EC2:

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 18:00; Tue 09:00 Tue 18:00
Name = web-01
```

RDS instance or cluster:

```text
Schedule = True
Schedule_Windows = Mon 08:30 Mon 19:00; Tue 08:30 Tue 19:00
Name = orders-db
```

Auto Scaling Group:

```text
Schedule = True
Schedule_Windows = Mon 08:00 Mon 20:00; Tue 08:00 Tue 20:00
Schedule_Asg_Min = 1
Schedule_Asg_Max = 3
Schedule_Asg_Desired = 2
Name = eks-workers
```

## Terraform Usage

Minimal:

```hcl
module "scheduler" {
  source = "git::https://github.com/tkfka1/terraform-aws-scheduler.git"

  accounts = [
    {
      account_id = "390844779767"
      region     = "ap-northeast-2"
      iam_role   = "testiam-schedule"
    }
  ]

  schedule_expression = "rate(5 minutes)"
  timezone            = "Asia/Seoul"
}
```

More complete:

```hcl
module "scheduler" {
  source = "git::https://github.com/tkfka1/terraform-aws-scheduler.git"

  accounts = [
    {
      account_id         = "390844779767"
      region             = "ap-northeast-2"
      iam_role           = "testiam-schedule"
      teams_webhook      = "https://outlook.office.com/webhook/REPLACE_ME"
      slack_webhook      = "https://hooks.slack.com/services/REPLACE_ME"
      telegram_bot_token = "123456:ABCDEF"
      telegram_chat_id   = "123456789"
      description        = "WEB-SERVER"
    }
  ]

  lambda_function_name   = "ec2-scheduler"
  lambda_role_name       = "ec2-scheduler-lambda"
  lambda_memory_size     = 256
  lambda_timeout_seconds = 300

  event_rule_name     = "ec2-scheduler-hourly"
  schedule_expression = "rate(5 minutes)"
  timezone            = "Asia/Seoul"
  log_level           = "INFO"

  enable_ec2 = true
  enable_rds = true
  enable_asg = true

  tag_schedule_key   = "Schedule"
  tag_schedule_value = "True"
  tag_window_key     = "Schedule_Windows"
  tag_asg_min_key    = "Schedule_Asg_Min"
  tag_asg_max_key    = "Schedule_Asg_Max"
  tag_asg_desired_key = "Schedule_Asg_Desired"

  notification_tag_keys = ["Name"]

  enable_verification        = true
  verification_delay_minutes = 30
  verification_table_name    = "scheduler-verification"
  verification_ttl_days      = 7

  enable_eventbridge_logging        = true
  eventbridge_log_group_name        = "/aws/events/ec2-scheduler-hourly"
  eventbridge_log_retention_in_days = 30

  tags = {
    Service = "scheduler"
    Owner   = "platform"
  }
}
```

## Account Object

Each entry in `accounts` supports:

- `account_id` required
- `region` required
- `iam_role` required, role name or full ARN
- `teams_webhook` optional
- `slack_webhook` optional
- `telegram_bot_token` optional
- `telegram_chat_id` optional
- `description` optional

## Target Account IAM Role

The scheduler Lambda assumes `iam_role` in each target account.
If `iam_role` is a name, the module expands it to:

```text
arn:aws:iam::<account_id>:role/<iam_role>
```

Trust policy for the target account role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<scheduler-account-id>:role/<lambda_role_name>"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Base EC2 permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:StartInstances",
        "ec2:StopInstances"
      ],
      "Resource": "*"
    }
  ]
}
```

Additional RDS permissions when `enable_rds = true`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "rds:DescribeDBInstances",
        "rds:DescribeDBClusters",
        "rds:ListTagsForResource",
        "rds:StartDBInstance",
        "rds:StopDBInstance",
        "rds:StartDBCluster",
        "rds:StopDBCluster"
      ],
      "Resource": "*"
    }
  ]
}
```

Additional ASG permissions when `enable_asg = true`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "autoscaling:DescribeAutoScalingGroups",
        "autoscaling:UpdateAutoScalingGroup"
      ],
      "Resource": "*"
    }
  ]
}
```

## Optional Features

Notifications:

- Teams is skipped when `teams_webhook` is empty.
- Slack is skipped when `slack_webhook` is empty.
- Telegram sends only when both `telegram_bot_token` and `telegram_chat_id` are set.
- When verification is enabled, immediate change notifications are suppressed and only verification results are sent.
- Notifications are sent only when changes occur or verification results exist.

Verification:

```hcl
enable_verification        = true
verification_delay_minutes = 30
verification_table_name    = "scheduler-verification"
verification_ttl_days      = 7
```

EventBridge logs:

```hcl
enable_eventbridge_logging        = true
eventbridge_log_group_name        = "/aws/events/ec2-scheduler-hourly"
eventbridge_log_retention_in_days = 30
```

## Inputs

- `accounts` required
- `lambda_function_name` default `ec2-scheduler`
- `lambda_role_name` default `ec2-scheduler-lambda`
- `lambda_memory_size` default `256`
- `lambda_timeout_seconds` default `300`
- `log_retention_in_days` default `30`
- `event_rule_name` default `ec2-scheduler-hourly`
- `schedule_expression` default `rate(5 minutes)`
- `enable_eventbridge_logging` default `false`
- `eventbridge_log_group_name` default `""`, which becomes `/aws/events/<event_rule_name>`
- `eventbridge_log_retention_in_days` default `30`
- `tags` default `{}`
- `log_level` default `INFO`
- `notification_tag_keys` default `[]`
- `enable_verification` default `false`
- `verification_delay_minutes` default `30`
- `verification_table_name` default `""`, which becomes `<lambda_function_name>-verification`
- `verification_ttl_days` default `7`
- `timezone` default `Asia/Seoul`
- `enable_ec2` default `true`
- `enable_rds` default `false`
- `enable_asg` default `false`
- `tag_schedule_key` default `Schedule`
- `tag_schedule_value` default `True`
- `tag_window_key` default `Schedule_Windows`
- `tag_asg_min_key` default `Schedule_Asg_Min`
- `tag_asg_max_key` default `Schedule_Asg_Max`
- `tag_asg_desired_key` default `Schedule_Asg_Desired`

## Outputs

- `lambda_function_name`
- `event_rule_arn`
- `lambda_role_arn`
- `eventbridge_log_group_name`
- `eventbridge_log_group_arn`
- `verification_table_name`
- `verification_table_arn`

## Notes

- This module does not create schedule tags on EC2, RDS, or ASG resources.
- If `Schedule_Windows` is missing or invalid, the resource is ignored.
- RDS uses the same tags on DB instances and clusters. Aurora uses cluster tags.
- ASG scheduling requires `Schedule_Asg_*` tags to exist on the ASG.
- If EKS self-managed nodes are managed by an ASG, schedule the ASG rather than individual instances.
