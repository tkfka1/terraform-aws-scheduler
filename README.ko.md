# terraform-aws-scheduler

Lambda + EventBridge 기반의 EC2, RDS, ASG 스케줄러 모듈입니다.
EventBridge 규칙에 맞춰 Lambda가 실행되고, 리소스 태그에 정의된 시간 윈도우를 기준으로 시작, 중지, 또는 ASG 용량 복원을 수행합니다.

저장소: https://github.com/tkfka1/terraform-aws-scheduler

## 개요

- EventBridge `rate(...)` 또는 `cron(...)` 스케줄로 실행
- 기본 시간대는 `Asia/Seoul`, 다른 시간대로 변경 가능
- EC2, RDS DB 인스턴스, RDS 클러스터, Auto Scaling Group 지원
- 대상 계정으로 `AssumeRole` 하여 크로스어카운트 실행
- Teams, Slack, Telegram 알림 지원
- DynamoDB 기반 지연 검증 옵션 지원
- 이미 원하는 상태인 리소스에는 중복 액션을 수행하지 않음

## 빠른 시작

1. 스케줄러 계정에 이 모듈을 배포합니다.
2. 대상 계정 IAM Role에 신뢰 정책을 추가합니다.
3. 대상 리소스에 `Schedule = True` 와 `Schedule_Windows = ...` 태그를 추가합니다.
4. 다음 EventBridge 주기에 Lambda가 실행되면 스케줄이 반영됩니다.

## 스케줄 태그 모델

일반 리소스는 아래 두 태그로 스케줄을 정의합니다.

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 18:00
```

규칙:

- `Schedule` 값은 설정된 enable 태그 키/값과 일치해야 합니다.
- `Schedule_Windows` 는 필수입니다. 값이 없거나 파싱에 실패하면 해당 리소스는 무시됩니다.
- 각 엔트리 형식은 `시작요일 시작시간 종료요일 종료시간` 입니다.
- 여러 엔트리는 `;` 또는 줄바꿈으로 구분합니다.
- 요일은 `Mon Tue Wed Thu Fri Sat Sun` 형식을 권장합니다. `Monday` 같은 전체 이름도 허용됩니다.
- 시간 형식은 `HH` 또는 `HH:MM` 입니다.
- 시작 시각은 포함, 종료 시각은 제외입니다.
- 종료 요일은 실제 종료되는 요일을 명시해야 합니다. 예를 들어 금요일 07:00부터 토요일 01:00까지라면 `Fri 07:00 Sat 01:00` 으로 적어야 합니다.
- `timezone` 값이 스케줄 계산 기준입니다. Lambda 실행 환경의 시스템 시간대와는 별개입니다.

관련 키 이름을 바꾸고 싶다면 아래 변수를 사용합니다.

- `tag_schedule_key`
- `tag_schedule_value`
- `tag_window_key`

## Schedule_Windows 예시

같은 날 안에서 끝나는 윈도우:

```text
Schedule = True
Schedule_Windows = Mon 10:00 Mon 12:00
```

자정을 넘기는 윈도우:

```text
Schedule = True
Schedule_Windows = Mon 22:00 Tue 02:00
```

금요일 아침부터 토요일 새벽까지:

```text
Schedule = True
Schedule_Windows = Fri 07:00 Sat 01:00
```

같은 날 두 개의 윈도우:

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 12:00; Mon 13:00 Mon 18:00
```

주중 반복:

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 18:00; Tue 09:00 Tue 18:00; Wed 09:00 Wed 18:00; Thu 09:00 Thu 18:00; Fri 09:00 Fri 18:00
```

주말만:

```text
Schedule = True
Schedule_Windows = Sat 10:00 Sat 16:00; Sun 10:00 Sun 16:00
```

## 리소스별 태그 예시

EC2:

```text
Schedule = True
Schedule_Windows = Mon 09:00 Mon 18:00; Tue 09:00 Tue 18:00
Name = web-01
```

RDS 인스턴스 또는 클러스터:

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

## Terraform 사용 예시

최소 구성:

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

조금 더 많은 옵션을 포함한 예시:

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

  tag_schedule_key    = "Schedule"
  tag_schedule_value  = "True"
  tag_window_key      = "Schedule_Windows"
  tag_asg_min_key     = "Schedule_Asg_Min"
  tag_asg_max_key     = "Schedule_Asg_Max"
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

## accounts 객체

`accounts` 배열의 각 항목은 아래 필드를 가집니다.

- `account_id` 필수
- `region` 필수
- `iam_role` 필수, Role 이름 또는 전체 ARN
- `teams_webhook` 선택
- `slack_webhook` 선택
- `telegram_bot_token` 선택
- `telegram_chat_id` 선택
- `description` 선택

## 대상 계정 IAM Role

스케줄러 Lambda는 각 대상 계정의 `iam_role` 을 AssumeRole 합니다.
`iam_role` 에 이름만 넣으면 아래 형식으로 확장됩니다.

```text
arn:aws:iam::<account_id>:role/<iam_role>
```

대상 계정 Role에는 아래와 같은 신뢰 정책이 필요합니다.

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

기본 EC2 권한:

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

`enable_rds = true` 인 경우 추가할 RDS 권한:

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

`enable_asg = true` 인 경우 추가할 ASG 권한:

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

## 선택 기능

알림:

- Teams 는 `teams_webhook` 이 비어 있으면 전송하지 않습니다.
- Slack 은 `slack_webhook` 이 비어 있으면 전송하지 않습니다.
- Telegram 은 `telegram_bot_token` 과 `telegram_chat_id` 가 모두 있어야 전송합니다.
- 알림은 실제 변경이 있거나 검증 결과가 있을 때만 보냅니다.

검증:

```hcl
enable_verification        = true
verification_delay_minutes = 30
verification_table_name    = "scheduler-verification"
verification_ttl_days      = 7
```

EventBridge 로그:

```hcl
enable_eventbridge_logging        = true
eventbridge_log_group_name        = "/aws/events/ec2-scheduler-hourly"
eventbridge_log_retention_in_days = 30
```

## 입력 변수

- `accounts` 필수
- `lambda_function_name` 기본값 `ec2-scheduler`
- `lambda_role_name` 기본값 `ec2-scheduler-lambda`
- `lambda_memory_size` 기본값 `256`
- `lambda_timeout_seconds` 기본값 `300`
- `log_retention_in_days` 기본값 `30`
- `event_rule_name` 기본값 `ec2-scheduler-hourly`
- `schedule_expression` 기본값 `rate(5 minutes)`
- `enable_eventbridge_logging` 기본값 `false`
- `eventbridge_log_group_name` 기본값 `""`, 실제 값은 `/aws/events/<event_rule_name>`
- `eventbridge_log_retention_in_days` 기본값 `30`
- `tags` 기본값 `{}`
- `log_level` 기본값 `INFO`
- `notification_tag_keys` 기본값 `[]`
- `enable_verification` 기본값 `false`
- `verification_delay_minutes` 기본값 `30`
- `verification_table_name` 기본값 `""`, 실제 값은 `<lambda_function_name>-verification`
- `verification_ttl_days` 기본값 `7`
- `timezone` 기본값 `Asia/Seoul`
- `enable_ec2` 기본값 `true`
- `enable_rds` 기본값 `false`
- `enable_asg` 기본값 `false`
- `tag_schedule_key` 기본값 `Schedule`
- `tag_schedule_value` 기본값 `True`
- `tag_window_key` 기본값 `Schedule_Windows`
- `tag_asg_min_key` 기본값 `Schedule_Asg_Min`
- `tag_asg_max_key` 기본값 `Schedule_Asg_Max`
- `tag_asg_desired_key` 기본값 `Schedule_Asg_Desired`

## 출력값

- `lambda_function_name`
- `event_rule_arn`
- `lambda_role_arn`
- `eventbridge_log_group_name`
- `eventbridge_log_group_arn`
- `verification_table_name`
- `verification_table_arn`

## 참고

- 이 모듈은 EC2, RDS, ASG 리소스에 스케줄 태그를 자동으로 생성하지 않습니다.
- `Schedule_Windows` 가 없거나 잘못되면 해당 리소스는 무시됩니다.
- RDS 는 DB 인스턴스와 클러스터에 동일한 태그 모델을 사용합니다. Aurora 는 클러스터 태그 기준입니다.
- ASG 스케줄링을 사용하려면 `Schedule_Asg_*` 태그가 반드시 필요합니다.
- EKS self-managed 노드가 ASG에 속해 있으면 개별 인스턴스보다 ASG 자체를 스케줄링하는 편이 안전합니다.
