variable "accounts" {
  description = "Target accounts configuration list."
  type = list(object({
    account_id          = string
    region              = string
    iam_role            = string
    teams_webhook       = optional(string)
    slack_webhook       = optional(string)
    telegram_bot_token  = optional(string)
    telegram_chat_id    = optional(string)
    description         = optional(string)
  }))
}


variable "lambda_function_name" {
  description = "Lambda function name."
  type        = string
  default     = "ec2-scheduler"
}

variable "lambda_role_name" {
  description = "IAM role name for Lambda."
  type        = string
  default     = "ec2-scheduler-lambda"
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 300
}

variable "log_retention_in_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 30
}

variable "event_rule_name" {
  description = "EventBridge rule name."
  type        = string
  default     = "ec2-scheduler-hourly"
}

variable "schedule_expression" {
  description = "EventBridge schedule expression (rate or cron)."
  type        = string
  default     = "rate(5 minutes)"
}

variable "enable_eventbridge_logging" {
  description = "Enable EventBridge rule logs to CloudWatch Logs."
  type        = bool
  default     = false
}

variable "eventbridge_log_group_name" {
  description = "CloudWatch log group name for EventBridge logs. Empty uses /aws/events/<event_rule_name>."
  type        = string
  default     = ""
}

variable "eventbridge_log_retention_in_days" {
  description = "EventBridge log retention in days."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags applied to resources."
  type        = map(string)
  default     = {}
}

variable "log_level" {
  description = "Lambda log level (DEBUG, INFO, WARNING, ERROR)."
  type        = string
  default     = "INFO"
}

variable "notification_tag_keys" {
  description = "Tag keys to include in notifications."
  type        = list(string)
  default     = []
}

variable "timezone" {
  description = "Timezone name for schedule evaluation."
  type        = string
  default     = "Asia/Seoul"
}

variable "enable_ec2" {
  description = "Enable EC2 scheduling."
  type        = bool
  default     = true
}

variable "enable_rds" {
  description = "Enable RDS scheduling."
  type        = bool
  default     = false
}

variable "enable_asg" {
  description = "Enable Auto Scaling Group scheduling."
  type        = bool
  default     = false
}

variable "tag_schedule_key" {
  description = "Tag key for schedule enablement."
  type        = string
  default     = "Schedule"
}

variable "tag_schedule_value" {
  description = "Tag value for schedule enablement."
  type        = string
  default     = "True"
}

variable "tag_start_key" {
  description = "Tag key for schedule start time."
  type        = string
  default     = "Schedule_Start"
}

variable "tag_stop_key" {
  description = "Tag key for schedule stop time."
  type        = string
  default     = "Schedule_Stop"
}

variable "tag_weekday_key" {
  description = "Tag key for allowed weekdays."
  type        = string
  default     = "Schedule_Weekend"
}

variable "tag_asg_min_key" {
  description = "Tag key for Auto Scaling Group min size restore."
  type        = string
  default     = "Schedule_Asg_Min"
}

variable "tag_asg_max_key" {
  description = "Tag key for Auto Scaling Group max size restore."
  type        = string
  default     = "Schedule_Asg_Max"
}

variable "tag_asg_desired_key" {
  description = "Tag key for Auto Scaling Group desired capacity restore."
  type        = string
  default     = "Schedule_Asg_Desired"
}
