output "https_url" {
  description = "CloudFront HTTPS URL for the HTTP edge. Null when no app routes."
  value       = module.app_infra.https_url
}

output "chatbot" {
  description = "The chat app's URL, image, login, and build result. Null when chatbot.enabled is false."
  value = local.chatbot_app == null ? null : {
    enabled        = true
    https_url      = module.app_infra.https_url
    image_uri      = "${local.app_image["chatbot"].ecr_repository_url}:${local.app_image["chatbot"].image_tag}"
    login_username = "demo"
    secret_name    = aws_secretsmanager_secret.app["chatbot"].name
    image_build    = try(jsondecode(data.local_file.build_info["chatbot"].content), null)
  }
}

output "chatbot_login_password" {
  description = "Demo login password (also in the app secret). Null when chatbot.enabled is false."
  value       = local.chatbot_app == null ? null : try(random_password.chatbot_demo_password[0].result, null)
  sensitive   = true
}

output "extra_apps" {
  description = "Per-app URL, path, image, and build result for overrides.extra_apps."
  value = {
    for k, app in var.overrides.extra_apps : k => {
      https_url    = module.app_infra.https_url
      path_pattern = try(local.apps[k].routing.path_pattern, null)
      image_uri    = "${local.app_image[k].ecr_repository_url}:${local.app_image[k].image_tag}"
      secret_name  = aws_secretsmanager_secret.app[k].name
      image_build  = try(jsondecode(data.local_file.build_info[k].content), null)
    }
  }
}

output "connection_string_public" {
  description = "Public connection string for the debug database user, for mongosh or a local app. Null when features.debug_access_for_cluster is false."
  value       = local.public_debug_connection_string
  sensitive   = true
}
