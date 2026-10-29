mock_provider "mongodbatlas" {
  override_during = plan

  mock_data "mongodbatlas_roles_org_id" {
    defaults = { org_id = "org123" }
  }

  # An empty mock_resource block makes Terraform generate known, per-instance
  # values for the computed attributes the outputs read; without it the values
  # stay unknown at plan and the assertions cannot run.
  mock_resource "mongodbatlas_project" {
    defaults = {}
  }

  mock_resource "mongodbatlas_cloud_provider_access_setup" {
    defaults = {
      role_id = "role-mock-id"
      aws_config = [{
        atlas_aws_account_arn          = "arn:aws:iam::123456789012:root"
        atlas_assumed_role_external_id = "external-id"
      }]
    }
  }

  mock_resource "mongodbatlas_cloud_provider_access_authorization" {
    defaults = {}
  }
}

mock_provider "aws" {
  override_during = plan

  mock_resource "aws_security_group" {
    defaults = {}
  }

  mock_resource "aws_vpc" {
    defaults = {}
  }

  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock-role" }
  }

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

run "resource_ids_expose_the_deployment_level_ids" {
  command = plan

  # The shared Atlas-AWS integration role only exists when a feature that needs
  # cloud provider access is on, so enable BYOK to exercise the non-null path.
  variables {
    features = { atlas_byok = true }
  }

  assert {
    condition = alltrue([
      output.resource_ids.project_id != null,
      output.resource_ids.project_id != "",
      output.resource_ids.cluster_name == local.resource_prefix,
      output.resource_ids.atlas_aws_role_id != null,
      output.resource_ids.atlas_aws_iam_role_arn != null,
    ])
    error_message = "resource_ids should surface the project id, cluster name, and the Atlas-AWS integration role id and ARN"
  }
}

run "region_maps_key_every_app_region_with_matching_key_sets" {
  command = plan

  assert {
    condition = alltrue([
      length(output.resource_ids.app_security_group_ids) == 1,
      length(output.resource_ids.vpc_ids) == 1,
      length(output.resource_ids.private_subnet_ids) == 1,
      toset(keys(output.resource_ids.app_security_group_ids)) == toset(keys(output.resource_ids.vpc_ids)),
      toset(keys(output.resource_ids.vpc_ids)) == toset(keys(output.resource_ids.private_subnet_ids)),
      contains(keys(output.resource_ids.app_security_group_ids), "us-east-1"),
      alltrue([for v in values(output.resource_ids.app_security_group_ids) : v != null && v != ""]),
      alltrue([for v in values(output.resource_ids.vpc_ids) : v != null && v != ""]),
      alltrue([for v in values(output.resource_ids.private_subnet_ids) : length(v) > 0]),
    ])
    error_message = "The app security group, VPC, and private subnet maps should share one non-empty key per app region"
  }
}

run "resource_prefix_names_the_cluster" {
  command = plan

  variables {
    overrides = { resource_prefix = "team-a" }
  }

  assert {
    condition     = output.resource_ids.cluster_name == "team-a"
    error_message = "cluster_name should track overrides.resource_prefix, which is the Atlas cluster name"
  }
}

run "two_app_regions_yield_two_keys_per_map" {
  command = plan

  variables {
    regions = [
      { name = "us-east-1", node_count = 3 },
      { name = "us-west-2", node_count = 2 },
    ]
    overrides = {
      extra_apps = {
        worker = { aws_region = "us-west-2" }
      }
    }
  }

  assert {
    condition = alltrue([
      length(output.resource_ids.app_security_group_ids) == 2,
      length(output.resource_ids.vpc_ids) == 2,
      length(output.resource_ids.private_subnet_ids) == 2,
      toset(keys(output.resource_ids.app_security_group_ids)) == toset(keys(output.resource_ids.vpc_ids)),
      toset(keys(output.resource_ids.vpc_ids)) == toset(keys(output.resource_ids.private_subnet_ids)),
      contains(keys(output.resource_ids.app_security_group_ids), "us-east-1"),
      contains(keys(output.resource_ids.app_security_group_ids), "us-west-2"),
      output.resource_ids.app_security_group_ids["us-east-1"] != output.resource_ids.app_security_group_ids["us-west-2"],
      output.resource_ids.vpc_ids["us-east-1"] != output.resource_ids.vpc_ids["us-west-2"],
    ])
    error_message = "An app in a second region should add that region as a key to every region map with distinct security group and VPC ids"
  }
}

run "byo_project_id_is_surfaced_not_looked_up" {
  command = plan

  variables {
    overrides = { project_id = "674619d870c247237f4b86a6" }
  }

  assert {
    condition     = output.resource_ids.project_id == "674619d870c247237f4b86a6"
    error_message = "resource_ids.project_id should surface overrides.project_id instead of looking it up"
  }
}

run "role_ids_are_null_without_cloud_provider_access_features" {
  command = plan

  assert {
    condition = alltrue([
      output.resource_ids.atlas_aws_role_id == null,
      output.resource_ids.atlas_aws_iam_role_arn == null,
    ])
    error_message = "resource_ids role id and ARN should be null when no feature that needs cloud provider access is enabled"
  }
}
