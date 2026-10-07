output "https_url" {
  description = "CloudFront HTTPS URL for the HTTP edge. Null when no app routes."
  value       = module.app_infra.https_url
}

output "chatbot" {
  description = "The chat app's image, login, secret, database access, region, IAM task role, ECS cluster and service names, log group, target group, and build result. Null when chatbot.enabled is false."
  value = local.chatbot_app == null ? null : merge(
    {
      enabled        = true
      login_username = "demo"
    },
    local.app_outputs["chatbot"]
  )
}

output "chatbot_login_password" {
  description = "Demo login password (also in the app secret). Null when chatbot.enabled is false."
  value       = local.chatbot_app == null ? null : try(random_password.chatbot_demo_password[0].result, null)
  sensitive   = true
}

output "extra_apps" {
  description = "Per-app path, image, secret, database access, region, IAM task role, ECS cluster and service names, log group, target group, and build result for overrides.extra_apps."
  value       = { for k in keys(var.overrides.extra_apps) : k => local.app_outputs[k] }
}

output "connection_string_public" {
  description = "Public connection string for the debug database user, for mongosh or a local app. Null when features.debug_access_for_cluster is false."
  value       = local.public_debug_connection_string
  sensitive   = true
}
