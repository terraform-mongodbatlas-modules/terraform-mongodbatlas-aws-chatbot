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
    defaults = { repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/app" }
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

mock_provider "local" {
  override_during = plan

  mock_data "local_file" {
    defaults = { content = jsonencode({ status = "SUCCEEDED" }) }
  }
}

mock_provider "http" {
  override_during = plan

  mock_data "http" {
    defaults = { response_body = "203.0.113.7\n" }
  }
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

run "ecr_off_brings_own_image" {
  command = plan

  variables {
    features = { ecr = false }
    chatbot  = { image_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/custom:1.0" }
  }

  assert {
    condition = alltrue([
      length(local.build_apps) == 0,
      length(aws_codebuild_project.image) == 0,
      length(aws_s3_bucket.source) == 0,
      output.chatbot.image_build == null,
      local.app_image["chatbot"].ecr_repository_url == "123456789012.dkr.ecr.us-east-1.amazonaws.com/custom",
      local.app_image["chatbot"].image_tag == "1.0",
    ])
    error_message = "features.ecr = false should skip the build and resolve the caller image"
  }
}

run "waf_off_disables_the_edge" {
  command = plan

  variables {
    features = { waf = false }
  }

  assert {
    condition     = local.http_edges["main"].waf.disabled == true
    error_message = "features.waf = false should disable the CloudFront WAF"
  }
}

run "vpc_endpoints_off_derives_nat" {
  command = plan

  variables {
    features = { vpc_endpoints = false }
  }

  assert {
    condition = alltrue([
      local.vpc_config.skip_interface_endpoints == true,
      local.ecs_apps["chatbot"].internet_egress == true,
      module.app_infra.aws.vpcs["us-east-1"].nat_gateway_enabled == true,
    ])
    error_message = "Skipping the interface endpoints should turn on NAT for the app"
  }
}

run "internet_egress_flag_turns_on_nat" {
  command = plan

  variables {
    features = { internet_egress = true }
  }

  assert {
    condition = alltrue([
      local.ecs_apps["chatbot"].internet_egress == true,
      module.app_infra.aws.vpcs["us-east-1"].nat_gateway_enabled == true,
    ])
    error_message = "features.internet_egress should turn on NAT without skipping endpoints"
  }
}

run "atlas_integrations_on" {
  command = plan

  variables {
    features = {
      atlas_byok             = true
      atlas_s3_log_export    = true
      atlas_s3_backup_export = true
    }
  }

  assert {
    condition = alltrue([
      local.atlas_aws_encryption.enabled == true,
      local.atlas_aws_encryption.create_kms_key.enabled == true,
      local.atlas_aws_log_integration.enabled == true,
      local.atlas_aws_log_integration.create_s3_bucket.enabled == true,
      local.atlas_aws_backup_export.enabled == true,
      local.atlas_aws_backup_export.create_s3_bucket.enabled == true,
    ])
    error_message = "The three Atlas integration flags should compile onto the atlas-aws module inputs"
  }
}

run "verify_flag_adds_the_poll" {
  command = plan

  variables {
    features = { verify_deployment_ready = true }
  }

  assert {
    condition     = length(terraform_data.verify) == 1
    error_message = "features.verify_deployment_ready should add one health poll"
  }
}

run "skip_tags_empties_the_map" {
  command = plan

  variables {
    overrides = { skip_tags = true }
  }

  assert {
    condition     = length(local.tags) == 0
    error_message = "overrides.skip_tags should set no tags"
  }
}

run "debug_access_resolves_the_caller_ip" {
  command = plan

  variables {
    features = { debug_access_for_cluster = true }
  }

  assert {
    condition = alltrue([
      local.debug_ip == "203.0.113.7",
      length(mongodbatlas_database_user.public_debug) == 1,
      length(data.http.caller_ip) == 1,
    ])
    error_message = "Debug access should resolve the caller IP and create the database user"
  }
}

run "debug_access_uses_allowed_ip_override" {
  command = plan

  variables {
    features  = { debug_access_for_cluster = true }
    overrides = { allowed_ip = "198.51.100.9" }
  }

  assert {
    condition = alltrue([
      local.debug_ip == "198.51.100.9",
      length(data.http.caller_ip) == 0,
    ])
    error_message = "overrides.allowed_ip should be used instead of resolving the caller IP"
  }
}
