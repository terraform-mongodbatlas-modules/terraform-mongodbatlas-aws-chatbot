terraform {
  required_version = ">= 1.10"

  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.16"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

provider "mongodbatlas" {}

# Deploys the chatbot app, its Atlas project and cluster, and the AWS infrastructure in one apply.
module "chatbot" {
  source = "../.."

  # Names the Atlas project, AWS resources, and app image; 1 to 23 lowercase characters.
  app_name = "springfield-health"

  # The healthcare corpus: the persona prompt, the four family chips, and the records under docs/.
  # A non-empty document_dirs replaces the module's bundled repository-docs corpus, and
  # skip_repo_docs stops it from being staged at all.
  chatbot        = { system_prompt = file("${path.module}/system_prompt.txt") }
  queries        = yamldecode(file("${path.module}/queries.yaml"))
  document_dirs  = ["${path.module}/docs"]
  skip_repo_docs = true

  # Brands the chat UI. assets/ overlays the rendered assets tree, so `.chainlit/config.toml`
  # sets the page title and description and everything else keeps the module default.
  assets_dir = "${path.module}/assets"

  # Every other input keeps its default: `features` for the opt-in WAF, VPC endpoints, encryption,
  # log and backup export, debug access, and readiness polling; `llm` for a keyed provider instead
  # of Bedrock; and `regions`, `overrides`, and `extra_tags` when you need them.
}

output "https_url" {
  description = "CloudFront HTTPS URL for the deployed chat UI."
  value       = module.chatbot.https_url
}

output "chatbot" {
  description = "The chat app's image, login, secret name, and build result."
  value       = module.chatbot.chatbot
}

output "chatbot_login_password" {
  description = "Demo login password (also stored in the app secret)."
  value       = module.chatbot.chatbot_login_password
  sensitive   = true
}
