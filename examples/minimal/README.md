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

The demo uses a single shared login. A real application would use its own authentication and authorization instead.

## Expected output

- `https_url`: the CloudFront URL for the chat UI.
- `chatbot.login_username`: `demo`.
- `chatbot_login_password`: the demo password (sensitive; also stored in the app secret).

## Prerequisites

If you are familiar with Terraform and already have Atlas API credentials and AWS credentials configured, go to [commands](#commands).

To deploy the hybrid search chatbot on AWS with Terraform:

1. Install [Terraform](https://developer.hashicorp.com/terraform/install) to be able to run `terraform` [commands](#commands).
2. [Sign in](https://account.mongodb.com/account/login) to or [create](https://account.mongodb.com/account/register) your MongoDB Atlas Account.
3. Configure your [authentication](https://registry.terraform.io/providers/mongodb/mongodbatlas/latest/docs#authentication) method. The module creates the Atlas project, so the credential needs access to your Atlas organization.

   **NOTE**: Service Accounts (SA) are the preferred authentication method. See [Grant Programmatic Access to an Organization](https://www.mongodb.com/docs/atlas/configure-api-access/#grant-programmatic-access-to-an-organization) in the MongoDB Atlas documentation for detailed instructions on configuring SA access to your project.

4. Configure your AWS credentials for the account and region you deploy into.

## Commands

```sh
terraform init # downloads the providers and creates a terraform.lock.hcl file
# configure authentication (AWS credentials and MONGODB_ATLAS_XXX env vars)
terraform apply
# open the chat UI at the CloudFront URL and sign in as `demo`
terraform output https_url
terraform output -raw chatbot_login_password
```

## Customize

This example sets the common inputs. For the full input reference, including `regions`, `assets_dir`, `document_dirs`, and `overrides`, see the [module README](../../README.md). The named internals are reached through `overrides`: your own VPC (`overrides.byo_vpc`), the cluster shape (`overrides.cluster`), a custom domain (`overrides.domain`), a fixed debug IP (`overrides.allowed_ip`), and extra apps (`overrides.extra_apps`).

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

# Deploys the chatbot app, its Atlas project and cluster, and the AWS infrastructure in one apply.
module "chatbot" {
  source = "terraform-mongodbatlas-modules/aws-chatbot/mongodbatlas"

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

  # UI questions keyed by the button label; {} keeps the bundled demo questions.
  queries = {
    "Why one database"    = "Why would an agent store retrieval and memory in the same database instead of a separate vector store?"
    "Why not Postgres"    = "Why would an agent use MongoDB instead of a relational database like PostgreSQL?"
    "Agent components"    = "What are the main components of an AI agent?"
    "Hybrid ranking"      = "How does $rankFusion combine keyword and vector search results?"
    "Agent memory"        = "How do I store short-term and long-term memory for an agent in MongoDB?"
    "Automated embedding" = "How does Automated Embedding generate vectors at index time and query time?"
    "How it was built"    = "How does the module build the app image and deploy it in one apply?"
    "Security posture"    = "What network and IAM controls does this deployment use?"
  }

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
```

## Tear down

Remove the whole stack, including the Atlas project and the AWS resources, with one command:

```sh
terraform destroy
```

## Feedback or Help

- If you have any feedback or trouble please open a GitHub Issue.
