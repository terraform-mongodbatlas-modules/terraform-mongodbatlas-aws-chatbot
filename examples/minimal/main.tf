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

# Deploys the chatbot app, its Atlas project and cluster, and the AWS infrastructure in one apply.
module "chatbot" {
  source = "../.."

  # Names the Atlas project, AWS resources, and app image; 1 to 23 lowercase characters.
  app_name = "mongodb-chatbot-demo"

  # Opt-in features; every flag defaults, so omit the ones you leave at the demo setting.
  features = {
    # Attach the AWS Managed Rules Common Rule Set to the CloudFront distribution.
    waf = true
    # Keep the interface VPC endpoints in the VPC instead of reaching AWS APIs over NAT.
    vpc_endpoints = true
    # Allow HTTPS egress from the app security group through NAT.
    internet_egress = false
    # Create a customer-managed KMS key and enable Atlas encryption at rest with it.
    atlas_byok = false
    # Export Atlas logs to a module-managed S3 bucket.
    atlas_s3_log_export = false
    # Export Atlas backups to a module-managed S3 bucket.
    atlas_s3_backup_export = false
    # Add the caller IP and a debugging database user with widened access.
    debug_access_for_cluster = false
    # Poll /health from the apply and fail on a timeout.
    verify_deployment_ready = true
  }

  # Chat app settings; omit to deploy the demo unchanged, or set image_url, container_size, db_access, or system_prompt.
  chatbot = {
    system_prompt = "Answer the question using only the context snippets in the user message. Start with a few short bullet points that give the direct answer, then add a short paragraph with the supporting details and any caveats. If the context is insufficient, say so briefly."
  }

  # LLM provider; bedrock (default) needs no key, while anthropic, openai, gemini, and grove need secret_name.
  llm = { provider = "bedrock" }

  # UI questions, in the order the chips appear; [] keeps the bundled demo questions.
  queries = [
    { label = "Why one database", message = "Why would an agent store retrieval and memory in the same database instead of a separate vector store?" },
    { label = "Why not Postgres", message = "Why would an agent use MongoDB instead of a relational database like PostgreSQL?" },
    { label = "Hybrid ranking", message = "How does $rankFusion combine keyword and vector search results?" },
    { label = "Agent memory", message = "How do I store short-term and long-term memory for an agent in MongoDB?" },
    { label = "Embedding freshness", message = "How does Automated Embedding keep vectors in sync when the underlying document changes?" },
    { label = "Security posture", message = "What network and IAM controls does this deployment use?" },
    { label = "Make it your own", message = "How do I make this demo my own?" },
  ]

  # Documents to ingest; the default ingests the bundled repository docs.
  # document_dirs = ["/bring/your/own/docs"]
  # skip_repo_docs = true

  # Tags merged over the module's Example and Name tags.
  extra_tags = var.extra_tags # Name = var.app_name added by default
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
