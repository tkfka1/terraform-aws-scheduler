output "lambda_function_name" {
  description = "Scheduler Lambda function name."
  value       = aws_lambda_function.scheduler.function_name
}

output "event_rule_arn" {
  description = "EventBridge rule ARN."
  value       = aws_cloudwatch_event_rule.hourly.arn
}

output "lambda_role_arn" {
  description = "Lambda IAM role ARN."
  value       = aws_iam_role.lambda.arn
}

output "eventbridge_log_group_name" {
  description = "EventBridge log group name (if enabled)."
  value       = var.enable_eventbridge_logging ? aws_cloudwatch_log_group.eventbridge[0].name : null
}

output "eventbridge_log_group_arn" {
  description = "EventBridge log group ARN (if enabled)."
  value       = var.enable_eventbridge_logging ? aws_cloudwatch_log_group.eventbridge[0].arn : null
}

output "verification_table_name" {
  description = "Verification DynamoDB table name (if enabled)."
  value       = var.enable_verification ? aws_dynamodb_table.verification[0].name : null
}

output "verification_table_arn" {
  description = "Verification DynamoDB table ARN (if enabled)."
  value       = var.enable_verification ? aws_dynamodb_table.verification[0].arn : null
}
