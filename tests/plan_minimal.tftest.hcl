mock_provider "mongodbatlas" {
  override_during = plan

  mock_data "mongodbatlas_roles_org_id" {
    defaults = { org_id = "org123" }
  }
}

mock_provider "aws" {
  override_during = plan

  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d", "us-east-1e", "us-east-1f"] }
  }

  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }

  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }

  mock_data "aws_region" {
    defaults = { name = "us-east-1" }
  }

  mock_data "aws_ec2_managed_prefix_list" {
    defaults = { id = "pl-cloudfront" }
  }

  mock_data "aws_cloudfront_cache_policy" {
    defaults = { id = "cache-disabled" }
  }

  mock_data "aws_cloudfront_origin_request_policy" {
    defaults = { id = "origin-req" }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      domain_name = "d111111abcdef8.cloudfront.net"
      id          = "E123456789"
    }
  }

  mock_resource "aws_cloudfront_vpc_origin" {
    defaults = { id = "vo-test" }
  }

  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/example/abc/def" }
  }

  mock_resource "aws_ecr_repository" {
    defaults = { repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mongodb-chatbot-demo" }
  }
}

mock_provider "random" {
  override_during = plan

  mock_resource "random_password" {
    defaults = { result = "test-password" }
  }
}

mock_provider "archive" {
  override_during = plan

  mock_data "archive_file" {
    defaults = {
      output_path         = ".build/app.zip"
      output_base64sha256 = "app-hash"
    }
  }
}

mock_provider "time" {
  override_during = plan
}

override_module {
  target          = module.atlas_cluster
  override_during = plan
  outputs = {
    connection_strings = {
      standard_srv = "mongodb+srv://cluster.example.mongodb.net"
      private_srv  = ""
      private_endpoint = [{
        srv_connection_string = "mongodb+srv://pl-0.example.mongodb.net"
        endpoints             = []
      }]
    }
  }
}

variables {
  app_name = "mongodb-chatbot-demo"
}

run "minimal_inputs_name_everything_from_app_name" {
  command = plan

  assert {
    condition = alltrue([
      local.atlas_org_id == "org123",
      local.aws_region == "us-east-1",
      local.apps["chatbot"].name == "mongodb-chatbot-demo",
      local.apps["chatbot"].runtime_secret_name == "mongodb-chatbot-demo-app",
      local.ecr_repositories["chatbot"].name == "mongodb-chatbot-demo",
      module.app_infra.ecs_apps["chatbot"].name == "mongodb-chatbot-demo",
      module.app_infra.ecs_apps["chatbot"].runtime_secret_name == "mongodb-chatbot-demo-app",
      module.ecs_service["chatbot"].ecs_cluster_name == "mongodb-chatbot-demo",
      module.ecs_service["chatbot"].ecs_service_name == "mongodb-chatbot-demo",
    ])
    error_message = "The project, AWS resources, ECR repository, ECS service, and app secret should all read app_name"
  }
}

run "built_image_resolves_to_the_module_repository" {
  command = plan

  assert {
    condition     = local.app_image["chatbot"].ecr_repository_url == module.app_infra.ecs_apps["chatbot"].ecr_repository_url
    error_message = "A built app should resolve to the module-managed ECR repository"
  }
}

run "outputs_expose_the_public_contract" {
  command = plan

  # `output.chatbot.image_uri` embeds `local.image_tags`, which is unknown at plan:
  # `data.archive_file.app` depends on `terraform_data.prepare_build_dirs`, so the
  # read defers to apply. The image tag is not asserted at plan for that reason.
  assert {
    condition = alltrue([
      startswith(output.https_url, "https://"),
      strcontains(output.https_url, "cloudfront.net"),
      output.chatbot.enabled == true,
      output.chatbot.login_username == "demo",
      output.chatbot_login_password == "test-password",
      length(output.extra_apps) == 0,
      output.connection_string_public == null,
    ])
    error_message = "The grouped outputs should resolve from the composed wiring"
  }
}

run "built_in_tags_reach_the_composed_modules" {
  command = plan

  assert {
    condition = alltrue([
      local.tags["Example"] == "atlas-aws-chatbot",
      local.tags["Name"] == "mongodb-chatbot-demo",
      length(module.app_infra.aws.ecs_task_roles) == 1,
    ])
    error_message = "The built-in Example and Name tags should be present by default"
  }
}

run "bare_document_name_resolves_to_the_bundled_corpus" {
  command = plan

  # Every bundled corpus name should resolve as a bare entry.
  variables {
    document_dirs = [
      "README.md",
      "architecture.md",
      "security-and-iam.md",
      "why-mongodb-for-agents.md",
      "minimal-example.md",
    ]
  }

  assert {
    condition     = length(var.document_dirs) == 5
    error_message = "A bare document_dirs name should validate against the bundled corpus"
  }
}

run "missing_document_entry_fails" {
  command = plan

  variables {
    document_dirs = ["does-not-exist.md"]
  }

  expect_failures = [var.document_dirs]
}

run "queries_move_the_assets_hash" {
  command = plan

  variables {
    queries = {
      "Why one database" = "Why would an agent store retrieval and memory in the same database instead of a separate vector store?"
    }
  }

  # The hash drives the image tag, so a change to queries must move it and start
  # one build. Compare against the same formula with empty queries.
  assert {
    condition = local.assets_content_hash != sha256(jsonencode({
      vendored       = local.vendored_assets_hash
      corpus         = local.corpus_sources_hash
      skip_repo_docs = var.skip_repo_docs
      queries        = {}
      document_dirs  = var.document_dirs
      override_files = local.assets_override_file_hashes
    }))
    error_message = "Setting queries should move local.assets_content_hash"
  }
}

run "bundled_corpus_maps_flat_names_to_repository_docs" {
  command = plan

  assert {
    condition = alltrue([
      contains(keys(local.corpus_sources), "README.md"),
      contains(keys(local.corpus_sources), "architecture.md"),
      contains(keys(local.corpus_sources), "security-and-iam.md"),
      contains(keys(local.corpus_sources), "why-mongodb-for-agents.md"),
      local.corpus_sources["minimal-example.md"] == "examples/minimal/README.md",
    ])
    error_message = "The bundled corpus should map each flat name to a repository doc"
  }
}

run "skip_repo_docs_moves_the_assets_hash" {
  command = plan

  variables {
    skip_repo_docs = true
  }

  assert {
    condition = local.assets_content_hash != sha256(jsonencode({
      vendored       = local.vendored_assets_hash
      corpus         = local.corpus_sources_hash
      skip_repo_docs = false
      queries        = var.queries
      document_dirs  = var.document_dirs
      override_files = local.assets_override_file_hashes
    }))
    error_message = "Setting skip_repo_docs should move local.assets_content_hash"
  }
}

run "bare_document_name_fails_when_repo_docs_skipped" {
  command = plan

  variables {
    skip_repo_docs = true
    document_dirs  = ["why-mongodb-for-agents.md"]
  }

  expect_failures = [var.document_dirs]
}

run "path_document_entry_still_works_when_repo_docs_skipped" {
  command = plan

  variables {
    skip_repo_docs = true
    document_dirs  = ["./docs"]
  }

  assert {
    condition     = length(var.document_dirs) == 1
    error_message = "A path document_dirs entry should validate with skip_repo_docs set"
  }
}

run "chatbot_system_prompt_reaches_the_container_env" {
  command = plan

  variables {
    chatbot = {
      system_prompt = "Answer in one sentence."
    }
  }

  assert {
    condition     = local.app_env.RAG_SYSTEM_PROMPT == "Answer in one sentence."
    error_message = "chatbot.system_prompt should land in the container env as RAG_SYSTEM_PROMPT"
  }
}

run "chatbot_system_prompt_is_omitted_by_default" {
  command = plan

  assert {
    condition     = !contains(keys(local.app_env), "RAG_SYSTEM_PROMPT")
    error_message = "An unset chatbot.system_prompt should leave the app default in place"
  }
}

run "extra_tags_merge_over_the_built_ins" {
  command = plan

  variables {
    extra_tags = { Owner = "demo", Name = "custom-name" }
  }

  assert {
    condition = alltrue([
      local.tags["Owner"] == "demo",
      local.tags["Name"] == "custom-name",
      local.tags["Example"] == "atlas-aws-chatbot",
    ])
    error_message = "extra_tags should merge over the built-in Name and Example tags"
  }
}

run "outputs_expose_the_per_app_runtime_handles" {
  command = plan

  # The ECS names, log group, and region are config-derived and known at plan;
  # the IAM role and target group ARNs are computed, so assert the keys only.
  assert {
    condition = alltrue([
      output.chatbot.aws_region == "us-east-1",
      output.chatbot.ecs_cluster_name == "mongodb-chatbot-demo",
      output.chatbot.ecs_service_name == "mongodb-chatbot-demo",
      output.chatbot.log_group_name == "/ecs/mongodb-chatbot-demo",
      output.chatbot.secret_name == "mongodb-chatbot-demo-app",
      output.chatbot.db_access.role_name == "readWrite",
      output.chatbot.db_access.namespaces == tolist(["hybrid_search.*"]),
      contains(keys(output.chatbot), "task_role_arn"),
      contains(keys(output.chatbot), "target_group_arn"),
    ])
    error_message = "The chatbot output should carry the ECS, log, IAM, target-group, and database-access handles"
  }
}
