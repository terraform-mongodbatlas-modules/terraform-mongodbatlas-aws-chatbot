output "https_url" {
  description = "CloudFront HTTPS URL for the app."
  value       = module.app_infra.aws.http_edges["main"].https_url
}

output "chainlit_demo_username" {
  description = "Demo login username."
  value       = "demo"
}

output "chainlit_demo_password" {
  description = "Demo login password (also in the app secret)."
  value       = random_password.chainlit_demo.result
  sensitive   = true
}

output "ecr_repository_url" {
  description = "ECR repository URL the module builds the app image into. Null when features.ecr is false."
  value       = var.features.ecr ? module.app_infra.ecs_apps["chatbot"].ecr_repository_url : null
}

output "image_build" {
  description = "CodeBuild result per built app: status, tag, duration, and log link."
  value = {
    for k, file in data.local_file.build_info : k => jsondecode(file.content)
  }
}

output "connection_string_public" {
  description = "Public connection string for the debug database user, for mongosh or a local app. Null when features.debug_access_for_cluster is false."
  value       = local.public_debug_connection_string
  sensitive   = true
}
