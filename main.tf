# Composition: the LLM resolver and the AWS app infra. The Atlas side lives in
# atlas.tf, the app secret and ECS service in app.tf. This file is wiring only;
# the locals live in locals.tf.

module "llm" {
  source = "./modules/llm"

  enable_llm   = true
  llm_provider = var.llm.provider
  secret_name  = var.llm.secret_name
  secret_value = try(data.aws_secretsmanager_secret_version.llm[0].secret_string, null)
  env_name     = coalesce(local.llm_env_name, "ANTHROPIC_API_KEY")
  env          = local.llm_env
  aws_region   = local.aws_region
}

data "aws_secretsmanager_secret_version" "llm" {
  count     = var.llm.secret_name != null ? 1 : 0
  region    = local.aws_region
  secret_id = var.llm.secret_name
}

module "app_infra" {
  source = "./modules/app-infra"

  default_resource_name_prefix = local.resource_prefix
  regions                      = var.regions
  tags                         = local.tags
  permissions_boundary         = var.overrides.permissions_boundary
  ecr_repositories             = local.ecr_repositories
  vpc_config                   = local.vpc_config
  http_edges                   = local.http_edges
  ecs_apps = {
    for k, app in local.ecs_apps : k => merge(app, {
      extra_task_policies = module.llm.task_policy_jsons
    })
  }
}
