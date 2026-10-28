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

output "resource_ids" {
  description = "Deployment-level resource IDs a caller would otherwise fetch with a data source: the Atlas project and cluster, the per-region app security group, VPC, and private subnets, and the shared Atlas-AWS integration role. The role id and ARN are null unless a feature that needs cloud provider access (BYOK, S3 log export, or S3 backup export) is enabled."
  value = {
    project_id             = module.atlas_project.id
    cluster_name           = local.resource_prefix
    app_security_group_ids = { for r in local.app_aws_regions : r => module.app_infra.aws.compute[r].app_security_group_id }
    vpc_ids                = { for r in local.app_aws_regions : r => module.app_infra.aws.vpcs[r].vpc_id }
    private_subnet_ids     = { for r in local.app_aws_regions : r => module.app_infra.aws.vpcs[r].private_subnet_ids }
    atlas_aws_role_id      = module.atlas_aws.role_id
    atlas_aws_iam_role_arn = module.atlas_aws.resource_ids.iam_role_arn
  }
}
