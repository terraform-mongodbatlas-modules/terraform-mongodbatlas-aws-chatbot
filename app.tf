# The app secret and the ECS service. The secret JSON the app stack reads is
# assembled here from the app-infra output, so one apply wires the app end to
# end.

resource "random_password" "chatbot_auth" {
  count   = var.chatbot.enabled ? 1 : 0
  length  = 64
  special = false
}

resource "random_password" "chatbot_demo_password" {
  count   = var.chatbot.enabled ? 1 : 0
  length  = 16
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  for_each = local.apps

  region                  = each.value.aws_region
  name                    = each.value.runtime_secret_name
  tags                    = local.tags
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "app" {
  for_each = local.apps

  region    = each.value.aws_region
  secret_id = aws_secretsmanager_secret.app[each.key].id
  secret_string = jsonencode(merge(
    {
      name               = each.value.name
      aws_region         = each.value.aws_region
      ecr_repository_url = local.app_image[each.key].ecr_repository_url
      network            = module.app_infra.ecs_apps[each.key].network
      iam                = module.app_infra.ecs_apps[each.key].iam
      routing = module.app_infra.ecs_apps[each.key].routing == null ? null : merge(
        module.app_infra.ecs_apps[each.key].routing,
        { health_check_path = "/" }
      )
      container = {
        env         = local.app_container_env[each.key]
        secret_keys = local.app_secret_keys[each.key]
      }
    },
    each.key == "chatbot" ? {
      CHAINLIT_AUTH_SECRET   = try(random_password.chatbot_auth[0].result, null)
      CHAINLIT_DEMO_PASSWORD = try(random_password.chatbot_demo_password[0].result, null)
    } : {},
    module.llm.secrets
  ))
}

module "ecs_service" {
  for_each = local.apps

  source = "./modules/ecs-service"

  name               = each.value.name
  aws_region         = each.value.aws_region
  ecr_repository_url = local.app_image[each.key].ecr_repository_url
  network            = module.app_infra.ecs_apps[each.key].network
  iam                = module.app_infra.ecs_apps[each.key].iam
  routing = module.app_infra.ecs_apps[each.key].routing == null ? null : {
    listener_arn      = module.app_infra.ecs_apps[each.key].routing.listener_arn
    listener_priority = module.app_infra.ecs_apps[each.key].routing.listener_priority
    path_pattern      = module.app_infra.ecs_apps[each.key].routing.path_pattern
    host_header       = module.app_infra.ecs_apps[each.key].routing.host_header
    container_port    = module.app_infra.ecs_apps[each.key].routing.container_port
    health_check_path = "/"
  }
  container = {
    env         = local.app_container_env[each.key]
    secret_keys = local.app_secret_keys[each.key]
    secret_arn  = aws_secretsmanager_secret.app[each.key].arn
  }
  task_cpu    = each.value.task_cpu
  task_memory = each.value.task_memory
  image_tag   = local.app_image[each.key].image_tag
  tags        = local.tags

  # A built image must exist before the service starts. `terraform_data.build`
  # is empty when `features.ecr` is false, and the dependency is then a no-op.
  depends_on = [terraform_data.build]
}
