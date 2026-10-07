# Minimal deployment

Deploy the hybrid search chatbot on AWS with MongoDB Atlas in one `terraform apply`.

The apply creates the following:

- An Atlas project and a sharded cluster, with the connection string wired to the app.
- The AWS app infrastructure: a VPC, an ECS service behind an Application Load Balancer, and a CloudFront distribution with the AWS Managed Rules Common Rule Set.
- The app image, built with CodeBuild from the vendored `chatbot/` source and pushed to a module-managed ECR repository.
- The demo login secret in AWS Secrets Manager.

`features.verify_deployment_ready = true` makes the apply poll `/health` until the app is ready. The app creates the search indexes and ingests the bundled corpus in a background task on startup, so the first apply ends at a reachable chat UI.

## Log in

Open the `https_url` in a browser and sign in with the demo credentials:

- Username: `demo`
- Password: `terraform output -raw chatbot_login_password`

## Expected output

- `https_url`: the CloudFront URL for the chat UI.
- `chatbot.login_username`: `demo`.
- `chatbot_login_password`: the demo password (sensitive; also stored in the app secret).

## Commands

```sh
terraform init # downloads the providers and creates a terraform.lock.hcl file
# configure authentication (AWS credentials and MONGODB_ATLAS_XXX env vars)
terraform apply
# open the chat UI at the CloudFront URL and sign in as `demo`
terraform output https_url
terraform output -raw chatbot_login_password
# cleanup
terraform destroy
```

## Code snippet

Copy and use this code to get started quickly:

**main.tf**

```hcl
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
  source = "terraform-mongodbatlas-modules/aws-chatbot/mongodbatlas"

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

  # The app answers with short bullet points first, then a paragraph of details.
  # Change the text to steer the answer shape; leave it out to keep the app default.
  chatbot = {
    system_prompt = "Answer the question using only the context snippets in the user message. Start with a few short bullet points that give the direct answer, then add a short paragraph with the supporting details and any caveats. If the context is insufficient, say so briefly."
  }
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
```

## Feedback or Help

- If you have any feedback or trouble please open a GitHub Issue.
