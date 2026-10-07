# `features.verify_deployment_ready`: poll `/health` after the service is up and
# fail the apply on a timeout. The poll is the same stdlib script `just
# public-test` runs, so the apply check and the pre-release smoke share one
# contract.

resource "terraform_data" "verify" {
  count = var.features.verify_deployment_ready && var.chatbot.enabled ? 1 : 0

  depends_on = [module.ecs_service]

  triggers_replace = [
    module.app_infra.https_url,
    try(local.image_tags["chatbot"], ""),
  ]

  provisioner "local-exec" {
    command = join(" ", [
      "python3 ${path.module}/scripts/health_poll.py",
      "--url ${module.app_infra.https_url}",
      "--timeout 900",
    ])
  }
}
