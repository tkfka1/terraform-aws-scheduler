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
