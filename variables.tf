# v1 top-level input surface. The flat inputs cover the common path; the
# `chatbot` object configures the vendored app; `overrides` holds the named
# internals, the BYO mechanisms, and `extra_apps`. The decision source of truth
# is docs/16/g16-13_atlas-aws-chatbot-v010.md.

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

    - `waf`: attach the AWS Managed Rules Common Rule Set to the CloudFront distribution.
    - `vpc_endpoints`: keep the interface VPC endpoints (ECR, logs, Secrets Manager, STS) in the VPC. Set false to skip them; the app then reaches AWS APIs over NAT, which the module enables.
    - `internet_egress`: allow HTTPS egress from the app security group through NAT.
    - `atlas_byok`: create a customer-managed KMS key and enable Atlas encryption at rest with it.
    - `atlas_s3_log_export`: export Atlas logs to a module-managed S3 bucket.
    - `atlas_s3_backup_export`: export Atlas backups to a module-managed S3 bucket.
    - `debug_access_for_cluster`: add a caller IP to the project access list and create a database user that borrows the first app's role and database, but intentionally widens collection-scoped access to the database level for debugging. With no apps, it falls back to `readWrite` on `hybrid_search`.
    - `verify_deployment_ready`: poll `/health` from the apply and fail on a timeout.
  EOT
  type = object({
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

  validation {
    condition     = !var.features.verify_deployment_ready || var.chatbot.enabled
    error_message = "features.verify_deployment_ready requires chatbot.enabled."
  }
}

variable "queries" {
  description = "Example questions rendered to `assets/demo_queries.yaml`, keyed by the label shown in the UI. Empty keeps the app's bundled file."
  type        = map(string)
  default     = {}
}

variable "document_dirs" {
  description = <<-EOT
    Documents copied into the image under `assets/document_dirs/`. Empty keeps the bundled corpus; a non-empty list replaces it. The bundled corpus is assembled from the repository docs unless `skip_repo_docs` is true. Each entry resolves one of three ways:

    - A bare name (no slash) resolves to the bundled corpus, for example `why-mongodb-for-agents.md`.
    - A path with a slash resolves relative to the working directory, for example `./docs/handbook/`.
    - An absolute path is used as-is.
  EOT
  type        = list(string)
  default     = []

  # A bare name must be a bundled corpus document. A path entry (with a slash)
  # bypasses this check and is validated by the rule below.
  validation {
    condition = alltrue([
      for entry in var.document_dirs :
      strcontains(entry, "/") || (
        !var.skip_repo_docs &&
        contains(keys(local.corpus_sources), entry)
      )
    ])
    error_message = "Each bare document_dirs name must be a bundled corpus document (${join(", ", sort(keys(local.corpus_sources)))}) and skip_repo_docs must be false."
  }

  # A path must exist relative to the working directory, or be absolute.
  validation {
    condition = alltrue([
      for entry in var.document_dirs :
      !strcontains(entry, "/") || (
        length(fileset(entry, "**")) > 0 ||
        try(fileexists(entry), false)
      )
    ])
    error_message = "Each document_dirs path must exist relative to the working directory or as an absolute path."
  }
}

variable "skip_repo_docs" {
  description = "Do not stage the repository docs into the bundled corpus. Set true to start with an empty corpus. A bare `document_dirs` name then fails validation, and only a path or absolute entry works."
  type        = bool
  default     = false
}

variable "assets_dir" {
  description = "Directory mirroring the app's `assets/` tree, copied over the rendered defaults. The branding mechanism: replace `.chainlit/config.toml`, `chainlit.md`, and `public/` without a per-file input."
  type        = string
  default     = null
}

variable "chatbot" {
  description = <<-EOT
    The vendored chat app. Enabled by default; every field defaults to the demo.

    - `enabled`: deploy the chatbot. Set false to deploy only `overrides.extra_apps`.
    - `image_url` / `dockerfile_path`: bring your own image, or build your own Dockerfile instead of the vendored app. Mutually exclusive.
    - `ecr`: null infers from the image source. Built apps keep a module-managed ECR repository; a pure `image_url` app skips it. Set true with `image_url` to keep the repository around during a rollback or cutover.
    - `container_size`: `small`, `medium`, or `large`; maps to the ECS task CPU and memory.
    - `task_cpu` / `task_memory`: exact ECS units, overriding `container_size`.
    - `system_prompt`: the RAG system prompt the app answers with. Null keeps the app default, which answers with short bullet points first and a paragraph of details after.
    - `db_access`: the database and role the app authenticates as.
    - `routing`: the path pattern and listener priority on the shared edge. Defaults to `/*` at priority 100.
    - `internet_egress`: allow HTTPS egress from the app security group through NAT.
    - `aws_region`: the app's AWS region. Defaults to the first entry in `regions`.
  EOT
  type = object({
    enabled         = optional(bool, true)
    image_url       = optional(string)
    dockerfile_path = optional(string)
    ecr             = optional(bool)
    container_size  = optional(string, "small")
    task_cpu        = optional(string)
    task_memory     = optional(string)
    system_prompt   = optional(string)
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
      }), {
      path_pattern      = ["/*"]
      host_header       = []
      listener_priority = 100
      container_port    = 8001
    })
    internet_egress = optional(bool, false)
    aws_region      = optional(string)
  })
  default = {}

  validation {
    condition     = var.chatbot.image_url == null || var.chatbot.dockerfile_path == null
    error_message = "chatbot: set image_url or dockerfile_path, not both."
  }

  validation {
    condition     = contains(["small", "medium", "large"], var.chatbot.container_size)
    error_message = "chatbot.container_size must be small, medium, or large."
  }

  validation {
    condition     = var.chatbot.dockerfile_path == null || fileexists(var.chatbot.dockerfile_path)
    error_message = "chatbot.dockerfile_path must point to an existing Dockerfile."
  }

  validation {
    condition = (
      var.chatbot.image_url != null ||
      var.chatbot.enabled == false ||
      try(var.chatbot.ecr, null) != false
    )
    error_message = "chatbot.ecr cannot be false when the chatbot image is module-built; leave it null or true, or set image_url."
  }
}

variable "llm" {
  description = "LLM provider for the app. Defaults to Amazon Bedrock, which uses the ECS task role and needs no key. Set `secret_name` for a keyed provider; the provider is inferred from the name unless set explicitly. Grove also requires `base_url`."
  type = object({
    provider    = optional(string, "bedrock")
    model       = optional(string)
    secret_name = optional(string)
    base_url    = optional(string)
  })
  default = {}

  validation {
    condition     = contains(["bedrock", "anthropic", "openai", "gemini", "grove"], var.llm.provider)
    error_message = "llm.provider must be bedrock, anthropic, openai, gemini, or grove."
  }

  validation {
    condition     = var.llm.provider != "grove" || var.llm.secret_name == null || try(var.llm.base_url, null) != null
    error_message = "llm.base_url is required when llm.provider = \"grove\" and llm.secret_name is set."
  }
}

variable "extra_tags" {
  description = "Additional tags merged over the module's built-in `Example` and `Name` tags. Set `overrides.skip_tags = true` to set no tags at all."
  type        = map(string)
  default     = {}
}

variable "overrides" {
  description = <<-EOT
    The named internals, the bring-your-own mechanisms, and `extra_apps`. Empty by default.

    - `byo_vpc`: a per-region map that replaces the managed VPC (`vpc_config.create = false`).
    - `cluster`: `cluster_type`, `shard_count`, `manual_scaling`, `auto_scaling.min_instance_size`, and `autoembed_model`.
    - `extra_apps`: a map of additional apps on the same cluster. Each entry supports `image_url` or `dockerfile_path`, nullable `ecr`, `container_size`, `db_access`, and `routing`. An entry with no `routing` is a private worker with no HTTP edge.
    - `networking`: the shared `main` edge every routing app uses.
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

    extra_apps = optional(map(object({
      image_url       = optional(string)
      dockerfile_path = optional(string)
      ecr             = optional(bool)
      container_size  = optional(string, "small")
      task_cpu        = optional(string)
      task_memory     = optional(string)
      db_access = optional(object({
        database_name   = optional(string, "hybrid_search")
        role_name       = optional(string, "readWrite")
        collection_name = optional(string)
      }), {})
      # No default: an omitted or null routing is a private worker with no
      # listener rule. A `/*` default would collide with the chatbot's rule.
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
    condition = (
      alltrue([
        for _, app in var.overrides.extra_apps :
        app.image_url == null || app.dockerfile_path == null
      ])
    )
    error_message = "overrides.extra_apps.*: set image_url or dockerfile_path, not both."
  }

  validation {
    condition = alltrue([
      for _, app in var.overrides.extra_apps :
      contains(["small", "medium", "large"], coalesce(app.container_size, "small"))
    ])
    error_message = "overrides.extra_apps.*.container_size must be small, medium, or large."
  }

  validation {
    condition = alltrue([
      for _, app in var.overrides.extra_apps :
      app.dockerfile_path == null || fileexists(app.dockerfile_path)
    ])
    error_message = "overrides.extra_apps.*.dockerfile_path must point to an existing Dockerfile."
  }

  # A non-chatbot app uses its map key as `name`, which drives the ECR
  # repository, ECS cluster/service/task family, ALB target group (32-char
  # limit), and IAM role names. Keep the key DNS-safe and short, and do not let
  # it collide with the chatbot's name (app_name) or the reserved `chatbot` key.
  validation {
    condition = alltrue([
      for k in keys(var.overrides.extra_apps) :
      length(k) <= 23 &&
      can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", k)) &&
      k != var.app_name &&
      k != "chatbot"
    ])
    error_message = "overrides.extra_apps keys must be 1 to 23 characters of lowercase letters, digits, and hyphens (start and end with a letter or digit), and must not equal app_name or chatbot."
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
    condition = alltrue([
      for _, app in var.overrides.extra_apps :
      app.image_url != null || try(app.ecr, null) != false
    ])
    error_message = "overrides.extra_apps.*.ecr cannot be false when that app image is module-built; leave it null or true, or set image_url."
  }
}
