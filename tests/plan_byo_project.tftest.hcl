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

# A passing plan proves the reference-mode validations too: the project module
# rejects a plan that passes `name`, `org_id`, or `tags` together with `project_id`.
run "byo_project_references_supplied_id" {
  command = plan

  variables {
    overrides = { project_id = "674619d870c247237f4b86a6" }
  }

  assert {
    condition = alltrue([
      module.atlas_project.id == "674619d870c247237f4b86a6",
      length(data.mongodbatlas_roles_org_id.current) == 0,
    ])
    error_message = "A supplied overrides.project_id should be used and the organization should not be read"
  }
}

run "byo_project_wires_downstream" {
  command = plan

  variables {
    overrides = { project_id = "674619d870c247237f4b86a6" }
    features  = { debug_access_for_cluster = true }
  }

  assert {
    condition     = mongodbatlas_database_user.public_debug[0].project_id == "674619d870c247237f4b86a6"
    error_message = "Downstream resources should use the supplied project_id"
  }
}

run "managed_project_reads_org" {
  command = plan

  assert {
    condition = alltrue([
      length(data.mongodbatlas_roles_org_id.current) == 1,
      local.atlas_org_id == "org123",
    ])
    error_message = "The managed-project path should still read the organization"
  }
}
