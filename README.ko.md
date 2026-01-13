# terraform-aws-scheduler

Lambda + EventBridge로 동작하는 EC2/RDS/ASG 스케줄러 모듈입니다. EventBridge 스케줄(기본: 5분)을 기준으로 실행되며, 지정한 시간대(기본: Asia/Seoul)에서 태그에 따라 리소스를 시작/중지합니다.

저장소: https://github.com/tkfka1/terraform-aws-scheduler

## 기능

- EventBridge 스케줄(rate/cron)
- 태그 기반 시작/중지 (자정 넘김 로직 포함)
- 계정별 AssumeRole + 알림(Teams/Slack/Telegram)
- Idempotent 처리 (이미 원하는 상태면 아무 것도 안 함)
- RDS 인스턴스/클러스터 스케줄링 옵션
- Auto Scaling Group 스케줄링 옵션(EKS self-managed)
- EventBridge 로그(CloudWatch Logs) 옵션

## 대상

- EC2 인스턴스 (EKS self-managed 워커 노드는 EC2로 처리)
- RDS DB 인스턴스/클러스터
- Auto Scaling Group (EKS self-managed)

EKS self-managed 노드가 Auto Scaling Group에 속해 있으면, 인스턴스를 직접 중지할 때 ASG가 다시 띄울 수 있습니다. 이 경우 ASG 단위 스케줄링 또는 대체 동작 제어가 필요합니다.

## 스케줄 로직

- `start < stop` -> `start <= now < stop`
- `start > stop` (자정 넘김) -> `now >= start` 또는 `now < stop`
- `start == stop` -> 스킵

시간대는 설정 가능합니다(기본값: `Asia/Seoul`). 시간대 로드 실패 시 동작하지 않습니다.

## 스케줄 태그 (EC2/RDS/ASG)

- `Schedule = True`
- `Schedule_Start = 10` (시간 또는 `HH:MM`)
- `Schedule_Stop = 12` (시간 또는 `HH:MM`)
- `Schedule_Weekend = Mon,Tue,Wed,Thu,Fri,Sat,Sun` (필수, 지정된 요일만 동작)

태그 키/값은 변수로 변경 가능합니다.

이 모듈은 태그를 생성하지 않습니다. EC2/RDS/ASG 태그는 별도 Terraform이나 콘솔에서 적용하세요.

## 사용 예시 (최소)

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

## 사용 예시 (전체)

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
  lambda_timeout_seconds = 60
  log_retention_in_days  = 30
  event_rule_name        = "ec2-scheduler-hourly"
  schedule_expression    = "rate(5 minutes)"
  log_level              = "INFO"
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

GitHub 저장소에서 모듈로 가져와서 사용할 수 있습니다:

```hcl
module "scheduler" {
  source = "git::https://github.com/tkfka1/terraform-aws-scheduler.git?ref=v1.0.0"
  # ... 변수 설정 ...
}
```

## EventBridge 로그 (옵션)

EventBridge 규칙을 CloudWatch Logs 대상으로 기록하려면 아래 옵션을 사용합니다:

```hcl
enable_eventbridge_logging       = true
eventbridge_log_group_name       = "/aws/events/ec2-scheduler-hourly"
eventbridge_log_retention_in_days = 30
```

## ASG 참고사항

ASG 스케줄링은 `Schedule_Asg_*` 태그가 반드시 있어야 동작합니다. 스케줄러가 태그를 생성하지 않습니다.

## 입력 변수

- `accounts` (필수): 계정 설정 리스트
  - `account_id` (필수)
  - `region` (필수)
  - `iam_role` (필수, 이름 또는 ARN)
  - `teams_webhook` (옵션)
  - `slack_webhook` (옵션)
  - `telegram_bot_token` (옵션)
  - `telegram_chat_id` (옵션)
  - `description` (옵션)
- `lambda_function_name` (기본값: `ec2-scheduler`)
- `lambda_role_name` (기본값: `ec2-scheduler-lambda`)
- `lambda_memory_size` (기본값: `256`)
- `lambda_timeout_seconds` (기본값: `60`)
- `log_retention_in_days` (기본값: `30`)
- `event_rule_name` (기본값: `ec2-scheduler-hourly`)
- `schedule_expression` (기본값: `rate(5 minutes)`)
- `enable_eventbridge_logging` (기본값: `false`)
- `eventbridge_log_group_name` (기본값: `""`, `/aws/events/<event_rule_name>` 사용)
- `eventbridge_log_retention_in_days` (기본값: `30`)
- `tags` (기본값: `{}`)
- `log_level` (기본값: `INFO`)
- `timezone` (기본값: `Asia/Seoul`)
- `enable_ec2` (기본값: `true`)
- `enable_rds` (기본값: `false`)
- `enable_asg` (기본값: `false`)
- `tag_schedule_key` (기본값: `Schedule`)
- `tag_schedule_value` (기본값: `True`)
- `tag_start_key` (기본값: `Schedule_Start`)
- `tag_stop_key` (기본값: `Schedule_Stop`)
- `tag_weekday_key` (기본값: `Schedule_Weekend`)
- `tag_asg_min_key` (기본값: `Schedule_Asg_Min`)
- `tag_asg_max_key` (기본값: `Schedule_Asg_Max`)
- `tag_asg_desired_key` (기본값: `Schedule_Asg_Desired`)

## 출력

- `lambda_function_name`
- `event_rule_arn`
- `lambda_role_arn`
- `eventbridge_log_group_name`
- `eventbridge_log_group_arn`

## 대상 계정 IAM Role

스케줄러 Lambda는 각 계정의 `iam_role`을 AssumeRole 합니다. 역할 이름 또는 ARN을 넣을 수 있으며, 이름을 넣으면 `arn:aws:iam::<account_id>:role/<iam_role>` 형식으로 확장됩니다.

대상 계정의 역할에 아래 Trust Policy를 추가해 스케줄러 Lambda 역할의 AssumeRole을 허용해야 합니다. Principal에는 모듈 출력 `lambda_role_arn`을 넣으세요.

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

각 계정의 `iam_role`에는 아래 권한이 필요합니다.

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

`enable_rds = true`일 때는 RDS 권한도 필요합니다.

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

`enable_asg = true`일 때는 ASG 권한도 필요합니다.

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

## 알림

- Teams/Slack은 값이 비어 있으면 전송하지 않습니다.
- Telegram은 `telegram_bot_token`과 `telegram_chat_id`가 모두 있어야 전송합니다.
- 변경사항이 있을 때만 알림을 보냅니다.

## 참고

- Lambda는 자신의 인스턴스 프로파일로 AssumeRole 합니다.
- 이 모듈은 태그를 생성하지 않습니다. EC2/RDS/ASG 태그는 별도로 적용해야 합니다.
- `Schedule_Weekend` 태그가 없으면 해당 인스턴스는 대상에서 제외됩니다.
- 스케줄 태그가 유효하지 않으면 해당 인스턴스는 제외됩니다.
- RDS는 DB 인스턴스/클러스터에 동일한 태그를 사용합니다(Aurora는 클러스터 태그).
- ASG 스케줄링은 `Schedule_Asg_*` 태그가 반드시 있어야 동작합니다.
