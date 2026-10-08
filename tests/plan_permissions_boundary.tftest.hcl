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

# Terraform test does not expose a child module's resources through
# `module.app_infra`, so the ECS roles are read back from the module's
# `ecs_apps[*].iam` output, which carries each role's boundary.
run "boundary_reaches_every_created_role" {
  command = plan

  variables {
    overrides = {
      permissions_boundary = "arn:aws:iam::123456789012:policy/b"
    }
  }

  assert {
    condition = alltrue([
      aws_iam_role.codebuild[0].permissions_boundary == "arn:aws:iam::123456789012:policy/b",
      module.app_infra.ecs_apps["chatbot"].iam.task_role_permissions_boundary == "arn:aws:iam::123456789012:policy/b",
      module.app_infra.ecs_apps["chatbot"].iam.task_execution_role_permissions_boundary == "arn:aws:iam::123456789012:policy/b",
      local.atlas_aws_encryption.iam_role.permissions_boundary == "arn:aws:iam::123456789012:policy/b",
      local.atlas_aws_log_integration.iam_role.permissions_boundary == "arn:aws:iam::123456789012:policy/b",
      local.atlas_aws_backup_export.iam_role.permissions_boundary == "arn:aws:iam::123456789012:policy/b",
    ])
    error_message = "A set permissions_boundary should reach the CodeBuild role, both ECS roles, and the Atlas AWS integration inputs"
  }
}

run "boundary_defaults_to_null" {
  command = plan

  assert {
    condition = alltrue([
      aws_iam_role.codebuild[0].permissions_boundary == null,
      module.app_infra.ecs_apps["chatbot"].iam.task_role_permissions_boundary == null,
      module.app_infra.ecs_apps["chatbot"].iam.task_execution_role_permissions_boundary == null,
      local.atlas_aws_encryption.iam_role.permissions_boundary == null,
      local.atlas_aws_log_integration.iam_role.permissions_boundary == null,
      local.atlas_aws_backup_export.iam_role.permissions_boundary == null,
    ])
    error_message = "An unset permissions_boundary should leave the CodeBuild role, both ECS roles, and the Atlas AWS integration inputs unbounded"
  }
}
