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

variable "extra_tags" {
  description = "Additional tags merged over the module's built-in Example and Name tags."
  type        = map(string)
  default     = {}
}

module "chatbot" {
  source = "../.."

  app_name = "mongodb-chatbot-demo"

  features = {
    waf                      = true
    vpc_endpoints            = true
    internet_egress          = false
    atlas_byok               = false
    atlas_s3_log_export      = false
    atlas_s3_backup_export   = false
    debug_access_for_cluster = false
    verify_deployment_ready  = true
  }

  queries = {
    "Why one database"    = "Why would an agent store retrieval and memory in the same database instead of a separate vector store?"
    "Why not Postgres"    = "Why would an agent use MongoDB instead of a relational database like PostgreSQL?"
    "Agent components"    = "What are the main components of an AI agent?"
    "Hybrid ranking"      = "How does $rankFusion combine keyword and vector search results?"
    "Agent memory"        = "How do I store short-term and long-term memory for an agent in MongoDB?"
    "Automated embedding" = "How does Automated Embedding generate vectors at index time and query time?"
  }

  document_dirs = ["why-mongodb-for-agents.md"] # [] keeps the bundled corpus
  llm           = { provider = "bedrock" }
  extra_tags    = var.extra_tags # Name = var.app_name added by default
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
