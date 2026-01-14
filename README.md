# terraform-aws-scheduler

EC2/RDS/ASG scheduler module using Lambda + EventBridge. It runs on an EventBridge schedule (default: every 5 minutes) and starts/stops resources based on tag-driven windows in a configurable timezone (default: Asia/Seoul).

Repository: https://github.com/tkfka1/terraform-aws-scheduler

## Features

- EventBridge schedule (rate/cron)
- Tag-driven start/stop with wrap-around midnight logic
- Cross-account assume role with notifications (Teams/Slack/Telegram)
- Idempotent: no action if already in desired state
- Optional RDS instance/cluster scheduling
- Optional Auto Scaling Group scheduling (EKS self-managed)
- Optional EventBridge logs to CloudWatch Logs
- Optional extra tag values in notifications
- Optional delayed verification of start/stop/scale actions (DynamoDB)

## Targets

- EC2 instances (EKS self-managed worker nodes are EC2)
- RDS DB instances and clusters
- Auto Scaling Groups (EKS self-managed)

If EKS self-managed nodes are in Auto Scaling Groups, stopping individual instances may be replaced by the ASG. In that case, schedule at the ASG level or disable replacement.

## Scheduling Logic

- `start < stop` -> `start <= now < stop`
- `start > stop` (crosses midnight) -> `now >= start` OR `now < stop`
- `start == stop` -> skip

Timezone is configurable (default: `Asia/Seoul`). If the timezone cannot be loaded, the function exits without doing anything.

## Schedule Tags (EC2)

Example (EC2 instance tags):

```
Schedule = True
Schedule_Start = 10
Schedule_Stop = 12
Schedule_Weekend = Mon,Tue,Wed,Thu,Fri
Name = web-01
```

## Schedule Tags (RDS)

Example (DB instance or cluster tags):

```
Schedule = True
Schedule_Start = 09:00
Schedule_Stop = 18:00
Schedule_Weekend = Mon,Tue,Wed,Thu,Fri
Name = orders-db
```

## Schedule Tags (ASG)

Example (Auto Scaling Group tags):

```
Schedule = True
Schedule_Start = 08
Schedule_Stop = 20
Schedule_Weekend = Mon,Tue,Wed,Thu,Fri
Schedule_Asg_Min = 1
Schedule_Asg_Max = 3
Schedule_Asg_Desired = 2
Name = eks-workers
```

Tag keys/values can be customized via module variables.

This module does not create tags. Apply tags on EC2/RDS/ASG with your own Terraform or the console.
You can include extra tag values in notifications with `notification_tag_keys` (e.g., `["Name"]`).

## Schedule Tag Patterns

Weekdays only (Mon-Fri, 09:00-18:00):

```
Schedule = True
Schedule_Start = 09:00
Schedule_Stop = 18:00
Schedule_Weekend = Mon,Tue,Wed,Thu,Fri
```

Weekend only (Sat-Sun, 10-16):

```
Schedule = True
Schedule_Start = 10
Schedule_Stop = 16
Schedule_Weekend = Sat,Sun
```

Specific weekdays only (Mon/Wed/Fri, 10-14):

```
Schedule = True
Schedule_Start = 10
Schedule_Stop = 14
Schedule_Weekend = Mon,Wed,Fri
```

Overnight (crosses midnight, 22:00-02:00):

```
Schedule = True
Schedule_Start = 22:00
Schedule_Stop = 02:00
Schedule_Weekend = Mon,Tue,Wed,Thu,Fri,Sat,Sun
```

Lunch break exclusion:

Single tag set cannot express two windows (e.g., 09:00-12:00 and 13:00-18:00). Use custom logic or split the schedule across resources.

Skip (start == stop):

```
Schedule = True
Schedule_Start = 12
Schedule_Stop = 12
Schedule_Weekend = Mon,Tue,Wed,Thu,Fri,Sat,Sun
```

## Usage (Minimal)

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

## Usage (Full)

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
  log_retention_in_days  = 30
  event_rule_name        = "ec2-scheduler-hourly"
  schedule_expression    = "rate(5 minutes)"
  log_level              = "INFO"
  notification_tag_keys  = ["Name"]
  enable_verification           = true
  verification_delay_minutes    = 30
  verification_table_name       = "scheduler-verification"
  verification_ttl_days         = 7
  enable_eventbridge_logging       = true
  eventbridge_log_retention_in_days = 30

  tags = {
    Service = "scheduler"
    Owner   = "platform"
  }

  timezone   = "Asia/Seoul"
  enable_ec2 = true
  enable_rds = true
  enable_asg = true

  tag_schedule_key   = "Schedule"
  tag_schedule_value = "True"
  tag_start_key      = "Schedule_Start"
  tag_stop_key       = "Schedule_Stop"
  tag_weekday_key    = "Schedule_Weekend"
  tag_asg_min_key     = "Schedule_Asg_Min"
  tag_asg_max_key     = "Schedule_Asg_Max"
  tag_asg_desired_key = "Schedule_Asg_Desired"
}
```

You can also consume this module from GitHub:

```hcl
module "scheduler" {
  source = "git::https://github.com/tkfka1/terraform-aws-scheduler.git?ref=v1.0.0"
  # ... variables ...
}
```

## EventBridge Logs (Optional)

Enable CloudWatch Logs target for the EventBridge rule:

```hcl
enable_eventbridge_logging       = true
eventbridge_log_group_name       = "/aws/events/ec2-scheduler-hourly"
eventbridge_log_retention_in_days = 30
```

## Verification (Optional)

Record start/stop/scale actions in DynamoDB and verify after a delay. The scheduler reports:
`✅ 완료`, `⏳ 진행`, or `❌ 스케줄링 오류`.

```hcl
enable_verification        = true
verification_delay_minutes = 30
verification_table_name    = "scheduler-verification"
verification_ttl_days      = 7
```

## Auto Scaling Group Notes

ASG scheduling requires `Schedule_Asg_*` tags to exist on the ASG. The scheduler reads those tags to restore capacity.

## Inputs

- `accounts` (required): list of account objects
  - `account_id` (required)
  - `region` (required)
  - `iam_role` (required, name or ARN)
  - `teams_webhook` (optional)
  - `slack_webhook` (optional)
  - `telegram_bot_token` (optional)
  - `telegram_chat_id` (optional)
  - `description` (optional)
- `lambda_function_name` (default: `ec2-scheduler`)
- `lambda_role_name` (default: `ec2-scheduler-lambda`)
- `lambda_memory_size` (default: `256`)
- `lambda_timeout_seconds` (default: `300`)
- `log_retention_in_days` (default: `30`)
- `event_rule_name` (default: `ec2-scheduler-hourly`)
- `schedule_expression` (default: `rate(5 minutes)`)
- `enable_eventbridge_logging` (default: `false`)
- `eventbridge_log_group_name` (default: `""`, uses `/aws/events/<event_rule_name>`)
- `eventbridge_log_retention_in_days` (default: `30`)
- `tags` (default: `{}`)
- `log_level` (default: `INFO`)
- `notification_tag_keys` (default: `[]`)
- `enable_verification` (default: `false`)
- `verification_delay_minutes` (default: `30`)
- `verification_table_name` (default: `""`, uses `<lambda_function_name>-verification`)
- `verification_ttl_days` (default: `7`)
- `timezone` (default: `Asia/Seoul`)
- `enable_ec2` (default: `true`)
- `enable_rds` (default: `false`)
- `enable_asg` (default: `false`)
- `tag_schedule_key` (default: `Schedule`)
- `tag_schedule_value` (default: `True`)
- `tag_start_key` (default: `Schedule_Start`)
- `tag_stop_key` (default: `Schedule_Stop`)
- `tag_weekday_key` (default: `Schedule_Weekend`)
- `tag_asg_min_key` (default: `Schedule_Asg_Min`)
- `tag_asg_max_key` (default: `Schedule_Asg_Max`)
- `tag_asg_desired_key` (default: `Schedule_Asg_Desired`)

## Outputs

- `lambda_function_name`
- `event_rule_arn`
- `lambda_role_arn`
- `eventbridge_log_group_name`
- `eventbridge_log_group_arn`
- `verification_table_name`
- `verification_table_arn`

## Target Account IAM Role

The scheduler Lambda assumes the `iam_role` in each target account. You can pass a role name or an ARN; a name is expanded to `arn:aws:iam::<account_id>:role/<iam_role>`.

Add a trust policy in the target account role to allow the scheduler Lambda role to assume it. Use the module output `lambda_role_arn` as the principal:

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

The `iam_role` in each account must allow EC2 actions:

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

If `enable_rds = true`, add RDS permissions:

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

If `enable_asg = true`, add ASG permissions:

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

## Notifications

- Teams/Slack can be empty to skip that channel.
- Telegram only sends when both `telegram_bot_token` and `telegram_chat_id` are set.
- Notifications are sent when changes occur or verification results are available.

## Notes

- Lambda uses its instance profile to assume roles.
- This module does not create tags; apply schedule tags on EC2/RDS/ASG separately.
- If `Schedule_Weekend` tag is missing, the instance is ignored.
- If a schedule tag is invalid, the instance is ignored.
- RDS uses the same tags on DB instances or clusters (Aurora uses cluster tags).
- ASG scheduling requires `Schedule_Asg_*` tags to exist; the scheduler does not create tags.
