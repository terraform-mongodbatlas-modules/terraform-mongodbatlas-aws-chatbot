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

  # The org is read from the credential, so there is no `atlas_org_id` input.
  atlas_org_id = data.mongodbatlas_roles_org_id.current.org_id

  # --- Tags -------------------------------------------------------------------
  # The two built-ins are hard-coded and not overridable; `extra_tags` adds keys
  # on top, and `skip_tags` removes the whole map.
  tags = var.overrides.skip_tags ? {} : merge({
    Example = "atlas-aws-chatbot"
    Name    = var.app_name
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
  llm_env      = var.llm.model == null ? {} : { (local.llm_model_env_names[var.llm.provider]) = var.llm.model }

  # --- Apps -------------------------------------------------------------------
  # `chatbot` is the blessed key; the module deploys it even when `overrides.apps`
  # omits it. `try()` reads the merged map uniformly, so the literal `{}` default
  # and a caller's fully specified entry resolve the same way.
  apps = {
    for k, cfg in merge({ chatbot = {} }, var.overrides.apps) : k => {
      name                = k == "chatbot" ? var.app_name : k
      aws_region          = coalesce(try(cfg.aws_region, null), local.aws_region)
      image_url           = try(cfg.image_url, null)
      build_path          = try(cfg.build_path, null)
      container_size      = try(cfg.container_size, "small")
      task_cpu            = coalesce(try(cfg.task_cpu, null), local.container_sizes[try(cfg.container_size, "small")].cpu)
      task_memory         = coalesce(try(cfg.task_memory, null), local.container_sizes[try(cfg.container_size, "small")].memory)
      internet_egress     = try(cfg.internet_egress, false)
      ecr_key             = k
      runtime_secret_name = "${k == "chatbot" ? var.app_name : k}-app"

      db_access = {
        database_name   = coalesce(try(cfg.db_access.database_name, null), "hybrid_search")
        role_name       = coalesce(try(cfg.db_access.role_name, null), "readWrite")
        collection_name = try(cfg.db_access.collection_name, null)
      }

      # ecs-service always attaches a listener rule, so every app routes. The
      # blessed app keeps the demo routing when the caller omits it; a second
      # app must set a distinct listener_priority.
      routing = try(cfg.routing, null) == null ? {
        path_pattern      = ["/*"]
        host_header       = []
        listener_priority = 100
        container_port    = 8001
        } : {
        path_pattern      = coalesce(try(cfg.routing.path_pattern, null), ["/*"])
        host_header       = coalesce(try(cfg.routing.host_header, null), [])
        listener_priority = coalesce(try(cfg.routing.listener_priority, null), 100)
        container_port    = coalesce(try(cfg.routing.container_port, null), 8001)
      }
    }
  }

  container_sizes = {
    small  = { cpu = "512", memory = "1024" }
    medium = { cpu = "1024", memory = "2048" }
    large  = { cpu = "2048", memory = "4096" }
  }

  # Apps the module builds with CodeBuild: the blessed chatbot and any
  # `build_path` entry, when `features.ecr` is true. A caller `image_url` app is
  # never built.
  build_apps = {
    for k, app in local.apps : k => app
    if var.features.ecr && app.image_url == null
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

  app_container_env = {
    for k, app in local.apps : k => (
      k == "chatbot" ? merge(local.app_env, module.llm.env) : module.llm.env
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
  # One repository per app so app-infra can resolve every `ecr_key`. The
  # repository is unused when the app brings its own image.
  ecr_repositories = {
    for k, app in local.apps : k => {
      name                 = app.name
      region               = app.aws_region
      image_tag_mutability = "IMMUTABLE"
      force_delete         = true
      lifecycle_keep_count = 10
    }
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

  http_edges = {
    main = {
      waf = {
        disabled                    = !var.features.waf || try(var.overrides.networking.main.waf_disabled, false)
        common_rule_set_count_rules = local.chainlit_waf_count_rules
      }
      aliases             = coalesce(try(var.overrides.domain.aliases, null), [])
      acm_certificate_arn = try(var.overrides.domain.acm_certificate_arn, null)
    }
  }

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
        enabled                 = true
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
        name_prefix     = "${var.app_name}-logs-"
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
        name_prefix     = "${var.app_name}-backup-"
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
  # CLOUDP-452488 backs `connection_strings` with a data source that reads the
  # private-endpoint hostnames after the cluster and the endpoint exist. The
  # fallback chain keeps the module usable against a cluster release that still
  # reads the attribute off the resource.
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
  chatbot_app = local.apps["chatbot"]
  app_env = {
    CHAINLIT_DEMO_USERNAME = "demo"
    MONGODB_DATABASE       = local.chatbot_app.db_access.database_name
    MONGODB_URI            = local.mongo_iam_connection_strings_by_region[local.chatbot_app.aws_region]
    TOP_K                  = "20"
    CHUNK_MAX_TOKENS       = "512"
    AUTOEMBED_MODEL        = var.overrides.cluster.autoembed_model
    DOCUMENT_DIRS          = "/app/assets/document_dirs"
  }
}
