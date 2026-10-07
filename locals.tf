# Resolution and compilation. Every top-level input and every `overrides` key
# compiles here; no resource reads `var.overrides` directly.

locals {
  # --- Regions ----------------------------------------------------------------
  regions_resolved = [
    for r in var.regions : {
      aws_name   = replace(lower(r.name), "_", "-")
      atlas_name = upper(replace(replace(lower(r.name), "_", "-"), "-", "_"))
      node_count = r.node_count
    }
  ]
  aws_region  = local.regions_resolved[0].aws_name
  aws_regions = [for r in local.regions_resolved : r.aws_name]

  # --- Naming -----------------------------------------------------------------
  # One prefix names every resource the module creates. It defaults to app_name;
  # set it to give two deployments that share an AWS account and region distinct
  # names, or the same value to deliberately reuse names.
  resource_prefix = coalesce(var.overrides.resource_prefix, var.app_name)

  # The org is read from the credential, so there is no `atlas_org_id` input.
  atlas_org_id = data.mongodbatlas_roles_org_id.current.org_id

  # --- Bundled corpus ---------------------------------------------------------
  # The corpus ships in the image and is what the deployed chatbot answers from.
  # It is assembled from the repository docs at render time. The key is the flat
  # corpus name a caller uses in `document_dirs`; the value is the source file.
  corpus_sources = {
    "README.md"                 = "README.md"
    "architecture.md"           = "docs/architecture.md"
    "security-and-iam.md"       = "docs/security-and-iam.md"
    "why-mongodb-for-agents.md" = "docs/why-mongodb-for-agents.md"
    "make-it-your-own.md"       = "docs/make-it-your-own.md"
    "minimal-example.md"        = "examples/minimal/README.md"
  }

  # --- Tags -------------------------------------------------------------------
  # The two built-ins are hard-coded and not overridable; `extra_tags` adds keys
  # on top, and `skip_tags` removes the whole map.
  tags = var.overrides.skip_tags ? {} : merge({
    Example = "atlas-aws-chatbot"
    Name    = local.resource_prefix
  }, var.extra_tags)

  # --- LLM provider -----------------------------------------------------------
  llm_env_names = {
    anthropic = "ANTHROPIC_API_KEY"
    openai    = "OPENAI_API_KEY"
    gemini    = "GEMINI_API_KEY"
    grove     = "GROVE_API_KEY"
  }
  llm_model_env_names = {
    bedrock   = "BEDROCK_MODEL"
    anthropic = "ANTHROPIC_MODEL"
    openai    = "OPENAI_MODEL"
    gemini    = "GEMINI_MODEL"
    grove     = "GROVE_MODEL"
  }
  llm_env_name = lookup(local.llm_env_names, var.llm.provider, null)
  llm_env = merge(
    var.llm.model == null ? {} : { (local.llm_model_env_names[var.llm.provider]) = var.llm.model },
    var.llm.provider == "grove" && try(var.llm.base_url, null) != null ? { GROVE_BASE_URL = var.llm.base_url } : {}
  )

  # --- Apps -------------------------------------------------------------------
  # `chatbot` is the vendored app; `overrides.extra_apps` are additional apps.
  # The chatbot is absent when disabled, so `try()` reads the merged map
  # uniformly. A `null` routing (an extra app with no `routing`) is a private
  # worker with no listener rule.
  apps_input = merge(
    var.chatbot.enabled ? { chatbot = var.chatbot } : {},
    var.overrides.extra_apps
  )

  # The chatbot takes the bare prefix; an extra app is prefixed so two
  # deployments that reuse a key do not collide.
  app_names = {
    for k in keys(local.apps_input) : k => (
      k == "chatbot" ? local.resource_prefix : "${local.resource_prefix}-${k}"
    )
  }

  apps = {
    for k, cfg in local.apps_input : k => {
      name                = local.app_names[k]
      aws_region          = coalesce(try(cfg.aws_region, null), local.aws_region)
      image_url           = try(cfg.image_url, null)
      dockerfile_path     = try(cfg.dockerfile_path, null)
      ecr                 = coalesce(try(cfg.ecr, null), try(cfg.image_url, null) == null)
      container_size      = try(cfg.container_size, "small")
      task_cpu            = coalesce(try(cfg.task_cpu, null), local.container_sizes[try(cfg.container_size, "small")].cpu)
      task_memory         = coalesce(try(cfg.task_memory, null), local.container_sizes[try(cfg.container_size, "small")].memory)
      internet_egress     = try(cfg.internet_egress, false)
      ecr_key             = coalesce(try(cfg.ecr, null), try(cfg.image_url, null) == null) ? k : null
      runtime_secret_name = "${local.app_names[k]}-app"

      db_access = {
        database_name   = coalesce(try(cfg.db_access.database_name, null), "hybrid_search")
        role_name       = coalesce(try(cfg.db_access.role_name, null), "readWrite")
        collection_name = try(cfg.db_access.collection_name, null)
      }

      # The chatbot's type defaults `routing` to the demo; an extra app with no
      # `routing` stays null and gets no listener rule.
      routing = try(cfg.routing, null) == null ? null : {
        path_pattern      = coalesce(try(cfg.routing.path_pattern, null), ["/*"])
        host_header       = coalesce(try(cfg.routing.host_header, null), [])
        listener_priority = coalesce(try(cfg.routing.listener_priority, null), 100)
        container_port    = coalesce(try(cfg.routing.container_port, null), 8001)
      }
    }
  }

  routing_apps = {
    for k, app in local.apps : k => app if app.routing != null
  }

  container_sizes = {
    small  = { cpu = "512", memory = "1024" }
    medium = { cpu = "1024", memory = "2048" }
    large  = { cpu = "2048", memory = "4096" }
  }

  # Apps the module builds with CodeBuild: the blessed chatbot and any
  # `dockerfile_path` entry. A caller `image_url` app is never built.
  build_apps = {
    for k, app in local.apps : k => app
    if app.image_url == null
  }

  # --- App image --------------------------------------------------------------
  # A built app resolves to the module's ECR repository and the content-addressed
  # tag; an app that brings its own image splits the URI into repo and tag.
  image_url_parts = {
    for k, app in local.apps : k => (
      app.image_url == null ? null : split(":", app.image_url)
    )
  }
  app_image = {
    for k, app in local.apps : k => (
      app.image_url == null
      ? {
        ecr_repository_url = module.app_infra.ecs_apps[k].ecr_repository_url
        image_tag          = local.image_tags[k]
      }
      : {
        ecr_repository_url = (
          length(local.image_url_parts[k]) > 1
          ? join(":", slice(local.image_url_parts[k], 0, length(local.image_url_parts[k]) - 1))
          : app.image_url
        )
        image_tag = (
          length(local.image_url_parts[k]) > 1
          ? element(local.image_url_parts[k], length(local.image_url_parts[k]) - 1)
          : "latest"
        )
      }
    )
  }

  common_app_env = {
    for k, app in local.apps : k => merge(module.llm.env, {
      MONGODB_DATABASE = app.db_access.database_name
      MONGODB_URI      = local.mongo_iam_connection_strings_by_region[app.aws_region]
    })
  }
  app_container_env = {
    for k, app in local.apps : k => (
      k == "chatbot" ? merge(local.common_app_env[k], local.app_env) : local.common_app_env[k]
    )
  }
  app_secret_keys = {
    for k, app in local.apps : k => (
      k == "chatbot"
      ? concat(["CHAINLIT_AUTH_SECRET", "CHAINLIT_DEMO_PASSWORD"], sort(keys(module.llm.secrets)))
      : sort(keys(module.llm.secrets))
    )
  }

  # --- app-infra inputs -------------------------------------------------------
  # Create repositories only for apps that resolve `ecr = true`. That is the
  # default for module-built images, inferred false for a pure `image_url` app,
  # and explicitly true for a BYO image that still wants to keep the repo around.
  ecr_repositories = {
    for k, app in local.apps : k => {
      name                 = app.name
      region               = app.aws_region
      image_tag_mutability = "IMMUTABLE"
      force_delete         = true
      lifecycle_keep_count = 10
    }
    if app.ecr
  }

  ecs_apps = {
    for k, app in local.apps : k => {
      name       = app.name
      ecr_key    = app.ecr_key
      aws_region = app.aws_region
      # app-infra requires NAT when the interface endpoints are skipped, so
      # derive egress from the flag instead of asking twice.
      internet_egress = app.internet_egress || var.features.internet_egress || !var.features.vpc_endpoints
      roles = [{
        role_name       = app.db_access.role_name
        database_name   = app.db_access.database_name
        collection_name = app.db_access.collection_name
      }]
      routing = app.routing == null ? null : {
        edge              = "main"
        listener_priority = app.routing.listener_priority
        path_pattern      = app.routing.path_pattern
        host_header       = app.routing.host_header
        container_port    = app.routing.container_port
      }
    }
  }

  app_aws_regions = toset([for app in local.apps : app.aws_region])

  # --- HTTP edge --------------------------------------------------------------
  # CRS SizeRestrictions_BODY blocks bodies over 8 KB. Chainlit POST /project/file
  # is a multipart upload and also trips BODY XSS/RFI/LFI.
  chainlit_waf_count_rules = [
    "SizeRestrictions_BODY",
    "CrossSiteScripting_BODY",
    "GenericRFI_BODY",
    "GenericLFI_BODY",
    "EC2MetaDataSSRF_BODY",
  ]

  # One edge serves every routing app; no edge when every app is a worker.
  http_edges = length(local.routing_apps) > 0 ? {
    main = {
      waf = {
        disabled                    = !var.features.waf || try(var.overrides.networking.main.waf_disabled, false)
        common_rule_set_count_rules = local.chatbot_app == null ? [] : local.chainlit_waf_count_rules
      }
      aliases             = coalesce(try(var.overrides.domain.aliases, null), [])
      acm_certificate_arn = try(var.overrides.domain.acm_certificate_arn, null)
    }
  } : {}

  vpc_config = {
    create                   = var.overrides.byo_vpc == null
    by_region                = coalesce(var.overrides.byo_vpc, {})
    skip_interface_endpoints = !var.features.vpc_endpoints
    bedrock_runtime_endpoint = module.llm.bedrock.enabled
  }

  # --- Atlas AWS integrations -------------------------------------------------
  kms_primary_region  = local.aws_region
  kms_replica_regions = toset([for r in local.aws_regions : r if r != local.kms_primary_region])

  atlas_aws_encryption = {
    enabled = var.features.atlas_byok
    private_endpoint_regions = (
      var.features.atlas_byok ? local.aws_regions : []
    )
    kms_key_arn = null
    region = (
      var.features.atlas_byok ? local.kms_primary_region : null
    )
    create_kms_key = (
      var.features.atlas_byok ? {
        # Scoped alias: the atlas-aws default `alias/atlas-encryption` is
        # account-global, so two BYOK deployments would collide on it.
        enabled                 = true
        alias                   = "alias/${local.resource_prefix}-atlas-encryption"
        deletion_window_in_days = 7
        enable_key_rotation     = true
        multi_region            = true
        replica_regions         = local.kms_replica_regions
      } : null
    )
  }

  atlas_aws_log_integration = {
    enabled = var.features.atlas_s3_log_export
    create_s3_bucket = (
      var.features.atlas_s3_log_export ? {
        enabled         = true
        force_destroy   = true
        name_prefix     = "${local.resource_prefix}-logs-"
        expiration_days = 90
      } : null
    )
    integrations = (
      var.features.atlas_s3_log_export ? [
        { log_types = ["MONGOD"], prefix_path = "operational" },
        { log_types = ["MONGOD_AUDIT"], prefix_path = "audit" },
      ] : null
    )
  }

  atlas_aws_backup_export = {
    enabled = var.features.atlas_s3_backup_export
    create_s3_bucket = (
      var.features.atlas_s3_backup_export ? {
        enabled         = true
        force_destroy   = true
        name_prefix     = "${local.resource_prefix}-backup-"
        expiration_days = 365
      } : null
    )
  }

  # --- Cluster ----------------------------------------------------------------
  cluster_regions = [
    for r in local.regions_resolved : {
      name       = r.atlas_name
      node_count = r.node_count
    }
  ]
  cluster_instance_size = try(var.overrides.cluster.manual_scaling.instance_size, null)
  cluster_auto_scaling = {
    compute_enabled           = var.overrides.cluster.manual_scaling == null
    compute_min_instance_size = var.overrides.cluster.auto_scaling.min_instance_size
    disk_gb_enabled           = true
  }

  # --- Mongo connection strings -----------------------------------------------
  # The cluster's own `connection_strings` attribute omits the private-endpoint
  # hostnames until the endpoints are wired, so prefer the private-endpoint SRV,
  # then `private_srv`, then `standard_srv`.
  mongo_private_connection_string = try(coalesce(
    try(module.atlas_cluster.connection_strings.private_endpoint[0].srv_connection_string, ""),
    try(module.atlas_cluster.connection_strings.private_srv, ""),
    module.atlas_cluster.connection_strings.standard_srv
  ), "NO_CONNECTION_STRING_AVAILABLE")

  aws_to_atlas_region = {
    for r in local.regions_resolved : r.aws_name => r.atlas_name
  }
  mongo_private_srv_by_atlas_region = merge([
    for pe in try(module.atlas_cluster.connection_strings.private_endpoint, []) : {
      for ep in try(pe.endpoints, []) :
      ep.region => pe.srv_connection_string
      if try(pe.srv_connection_string, "") != ""
    }
  ]...)
  mongo_private_connection_strings_by_region = {
    for region in local.app_aws_regions : region => coalesce(
      try(local.mongo_private_srv_by_atlas_region[local.aws_to_atlas_region[region]], ""),
      local.mongo_private_connection_string
    )
  }

  mongo_iam_auth_query = "authSource=%24external&authMechanism=MONGODB-AWS"

  mongo_iam_connection_strings_by_region = {
    for region, srv in local.mongo_private_connection_strings_by_region :
    region => (
      srv == "" || srv == "NO_CONNECTION_STRING_AVAILABLE"
      ? srv
      : strcontains(srv, "?")
      ? "${srv}&${local.mongo_iam_auth_query}"
      : "${srv}/?${local.mongo_iam_auth_query}"
    )
  }

  # --- App env ----------------------------------------------------------------
  # `chatbot_app` is null when the chatbot is disabled; `app_env` is then empty
  # and only the chatbot's container env reads it.
  chatbot_app = try(local.apps["chatbot"], null)
  app_env = local.chatbot_app == null ? {} : merge(
    {
      CHAINLIT_DEMO_USERNAME = "demo"
      TOP_K                  = "20"
      CHUNK_MAX_TOKENS       = "512"
      AUTOEMBED_MODEL        = var.overrides.cluster.autoembed_model
      DOCUMENT_DIRS          = "/app/assets/document_dirs"
    },
    var.chatbot.system_prompt == null ? {} : {
      RAG_SYSTEM_PROMPT = var.chatbot.system_prompt
    }
  )

  # The debug database user borrows the first app's role_name and
  # database_name. atlas.tf intentionally drops collection_name so the public
  # debug user gets database-level access for temporary investigation. The
  # chatbot is the default source; with it disabled, the first extra app is
  # used. With no apps at all, fall back to the module's default grant so the
  # caller can still connect to the cluster.
  debug_db_access = (
    local.chatbot_app != null ? local.chatbot_app.db_access :
    length(local.apps) > 0 ? values(local.apps)[0].db_access :
    {
      database_name   = "hybrid_search"
      role_name       = "readWrite"
      collection_name = null
    }
  )

  # --- App outputs ------------------------------------------------------------
  # One shape for `chatbot` and `extra_apps` so the two cannot drift. Every value
  # reads a resource this module already creates; the chatbot adds `enabled` and
  # `login_username` on top. `path_pattern` and `target_group_arn` are both null
  # for a private worker.
  app_outputs = {
    for k, app in local.apps : k => {
      aws_region       = app.aws_region
      path_pattern     = try(app.routing.path_pattern, null)
      image_uri        = "${local.app_image[k].ecr_repository_url}:${local.app_image[k].image_tag}"
      secret_name      = aws_secretsmanager_secret.app[k].name
      task_role_arn    = module.app_infra.ecs_apps[k].iam.task_role_arn
      ecs_cluster_name = module.ecs_service[k].ecs_cluster_name
      ecs_service_name = module.ecs_service[k].ecs_service_name
      log_group_name   = module.ecs_service[k].ecs_log_group_name
      target_group_arn = module.ecs_service[k].target_group_arn
      # The Atlas database user grant, as a role plus the namespaces it reaches.
      # A null collection_name is a database-wide grant, documented as `db.*`.
      db_access = {
        role_name = app.db_access.role_name
        namespaces = tolist([
          app.db_access.collection_name == null
          ? "${app.db_access.database_name}.*"
          : "${app.db_access.database_name}.${app.db_access.collection_name}"
        ])
      }
      image_build = contains(keys(terraform_data.build), k) ? {
        image_tag = local.app_image[k].image_tag
        project   = aws_codebuild_project.image[k].name
        region    = app.aws_region
      } : null
    }
  }
}
