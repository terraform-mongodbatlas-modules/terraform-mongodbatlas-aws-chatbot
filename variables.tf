# v1 top-level input surface. The flat inputs cover the common path; the
# `overrides` object holds the named internals and the BYO mechanisms. The
# decision source of truth is docs/16/g16-13_atlas-aws-chatbot-v010.md.

variable "app_name" {
  description = "Name for the Atlas project, the AWS resources, and the app image. Lowercase letters, digits, and hyphens; 1 to 23 characters so the Atlas cluster name is not truncated."
  type        = string

  validation {
    condition = (
      length(var.app_name) >= 1 &&
      length(var.app_name) <= 23 &&
      can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.app_name))
    )
    error_message = "app_name must be 1 to 23 characters of lowercase letters, digits, and hyphens, and must start and end with a letter or digit."
  }
}

variable "regions" {
  description = "Atlas cluster regions. Use AWS region names (for example us-east-1); the Atlas form (US_EAST_1) is also accepted. The app runs in the first region."
  type = list(object({
    name       = string
    node_count = optional(number, 3)
  }))
  default = [{ name = "us-east-1", node_count = 3 }]

  validation {
    condition     = length(var.regions) > 0
    error_message = "regions must contain at least one entry."
  }
}

variable "features" {
  description = <<-EOT
    Opt-in deployment features. The defaults produce a private, tagged demo:

    - `ecr`: create the ECR repository and build the app image with CodeBuild. Set false to skip both; every app entry must then supply `image_url`.
    - `waf`: attach the AWS Managed Rules Common Rule Set to the CloudFront distribution.
    - `vpc_endpoints`: keep the interface VPC endpoints (ECR, logs, Secrets Manager, STS) in the VPC. Set false to skip them; the app then reaches AWS APIs over NAT, which the module enables.
    - `internet_egress`: allow HTTPS egress from the app security group through NAT.
    - `atlas_byok`: create a customer-managed KMS key and enable Atlas encryption at rest with it.
    - `atlas_s3_log_export`: export Atlas logs to a module-managed S3 bucket.
    - `atlas_s3_backup_export`: export Atlas backups to a module-managed S3 bucket.
    - `debug_access_for_cluster`: add a caller IP to the project access list and create a full-access database user.
    - `verify_deployment_ready`: poll `/health` from the apply and fail on a timeout.
  EOT
  type = object({
    ecr                      = optional(bool, true)
    waf                      = optional(bool, true)
    vpc_endpoints            = optional(bool, true)
    internet_egress          = optional(bool, false)
    atlas_byok               = optional(bool, false)
    atlas_s3_log_export      = optional(bool, false)
    atlas_s3_backup_export   = optional(bool, false)
    debug_access_for_cluster = optional(bool, false)
    verify_deployment_ready  = optional(bool, false)
  })
  default = {}
}

variable "queries" {
  description = "Example questions rendered to `assets/demo_queries.yaml`, keyed by the label shown in the UI. Empty keeps the app's bundled file."
  type        = map(string)
  default     = {}
}

variable "document_dirs" {
  description = "Directories of documents copied into the image under `assets/document_dirs/`. Empty keeps the bundled corpus; a non-empty list replaces it."
  type        = list(string)
  default     = []
}

variable "assets_dir" {
  description = "Directory mirroring the app's `assets/` tree, copied over the rendered defaults. The branding mechanism: replace `.chainlit/config.toml`, `chainlit.md`, and `public/` without a per-file input."
  type        = string
  default     = null
}

variable "llm" {
  description = "LLM provider for the app. Defaults to Amazon Bedrock, which uses the ECS task role and needs no key. Set `secret_name` for a keyed provider; the provider is inferred from the name unless set explicitly."
  type = object({
    provider    = optional(string, "bedrock")
    model       = optional(string)
    secret_name = optional(string)
  })
  default = {}

  validation {
    condition     = contains(["bedrock", "anthropic", "openai", "gemini", "grove"], var.llm.provider)
    error_message = "llm.provider must be bedrock, anthropic, openai, gemini, or grove."
  }
}

variable "extra_tags" {
  description = "Additional tags merged over the module's built-in `Example` and `Name` tags. Set `overrides.skip_tags = true` to set no tags at all."
  type        = map(string)
  default     = {}
}

variable "overrides" {
  description = <<-EOT
    The named internals and the bring-your-own mechanisms. Empty by default.

    - `byo_vpc`: a per-region map that replaces the managed VPC (`vpc_config.create = false`).
    - `cluster`: `cluster_type`, `shard_count`, `manual_scaling`, `auto_scaling.min_instance_size`, and `autoembed_model`.
    - `apps`: a map of app entries. `chatbot` is the blessed key and deploys even when omitted.
    - `networking`: the shared `main` edge every app routes through.
    - `domain`: the custom-domain aliases and ACM certificate.
    - `allowed_ip`: a fixed debug IP instead of resolving the caller's.
    - `skip_tags`: set no tags at all.
  EOT
  type = object({
    byo_vpc = optional(map(object({
      vpc_id                  = string
      private_subnet_ids      = list(string)
      public_subnet_ids       = optional(list(string), [])
      vpc_cidr_block          = string
      private_route_table_ids = list(string)
    })))

    cluster = optional(object({
      cluster_type = optional(string, "SHARDED")
      shard_count  = optional(number, 1)
      manual_scaling = optional(object({
        instance_size = string
      }))
      auto_scaling = optional(object({
        min_instance_size = optional(string, "M30")
      }), {})
      autoembed_model = optional(string, "voyage-4-lite")
    }), {})

    apps = optional(map(object({
      image_url      = optional(string)
      build_path     = optional(string)
      container_size = optional(string, "small")
      task_cpu       = optional(string)
      task_memory    = optional(string)
      db_access = optional(object({
        database_name   = optional(string, "hybrid_search")
        role_name       = optional(string, "readWrite")
        collection_name = optional(string)
      }), {})
      routing = optional(object({
        path_pattern      = optional(list(string), ["/*"])
        host_header       = optional(list(string), [])
        listener_priority = optional(number, 100)
        container_port    = optional(number, 8001)
      }))
      internet_egress = optional(bool, false)
      aws_region      = optional(string)
    })), {})

    networking = optional(object({
      main = optional(object({
        waf_disabled = optional(bool, false)
      }), {})
    }), {})

    domain = optional(object({
      aliases             = optional(list(string))
      acm_certificate_arn = optional(string)
    }))

    allowed_ip = optional(string, "")
    skip_tags  = optional(bool, false)
  })
  default = {}

  validation {
    condition = alltrue([
      for _, app in var.overrides.apps :
      app.image_url == null || app.build_path == null
    ])
    error_message = "overrides.apps.*: set image_url or build_path, not both."
  }

  validation {
    condition = alltrue([
      for _, app in var.overrides.apps :
      contains(["small", "medium", "large"], coalesce(app.container_size, "small"))
    ])
    error_message = "overrides.apps.*.container_size must be small, medium, or large."
  }

  # A non-chatbot app uses its map key as `name`, which drives the ECR
  # repository, ECS cluster/service/task family, ALB target group (32-char
  # limit), and IAM role names. Keep the key DNS-safe and short, and do not let
  # it collide with the blessed chatbot's name (app_name).
  validation {
    condition = alltrue([
      for k in keys(var.overrides.apps) :
      length(k) <= 23 &&
      can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", k)) &&
      k != var.app_name
    ])
    error_message = "overrides.apps keys must be 1 to 23 characters of lowercase letters, digits, and hyphens (start and end with a letter or digit), and must not equal app_name."
  }

  validation {
    condition = var.overrides.byo_vpc == null || alltrue([
      for region in keys(var.overrides.byo_vpc) :
      contains([for r in var.regions : replace(lower(r.name), "_", "-")], region)
    ])
    error_message = "overrides.byo_vpc keys must match an AWS region in regions (for example us-east-1)."
  }

  validation {
    condition = var.overrides.domain == null || (
      length(coalesce(var.overrides.domain.aliases, [])) == 0 ||
      var.overrides.domain.acm_certificate_arn != null
    )
    error_message = "overrides.domain.acm_certificate_arn is required when overrides.domain.aliases is set."
  }

  validation {
    condition = var.features.ecr || (
      try(var.overrides.apps["chatbot"].image_url, null) != null &&
      alltrue([
        for _, app in var.overrides.apps :
        app.image_url != null && app.build_path == null
      ])
    )
    error_message = "features.ecr = false creates no repository, so every app entry (including chatbot) must set image_url and must not set build_path."
  }
}
