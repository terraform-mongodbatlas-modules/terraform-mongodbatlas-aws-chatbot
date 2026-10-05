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
  overrides = {
    byo_vpc = {
      "us-east-1" = {
        vpc_id                  = "vpc-east"
        private_subnet_ids      = ["subnet-a", "subnet-b"]
        vpc_cidr_block          = "10.0.0.0/16"
        private_route_table_ids = ["rtb-east"]
      }
    }
  }
}

run "byo_vpc_compiles_onto_the_app_infra_map" {
  command = plan

  assert {
    condition = alltrue([
      local.vpc_config.create == false,
      local.vpc_config.by_region["us-east-1"].vpc_id == "vpc-east",
      module.app_infra.operations.vpc_pin == null,
      module.app_infra.region_network["us-east-1"].private_subnet_ids == tolist(["subnet-a", "subnet-b"]),
      module.app_infra.region_network["us-east-1"].vpc_cidr_block == "10.0.0.0/16",
    ])
    error_message = "overrides.byo_vpc should reach app-infra as vpc_config.create = false with the by_region map"
  }
}
