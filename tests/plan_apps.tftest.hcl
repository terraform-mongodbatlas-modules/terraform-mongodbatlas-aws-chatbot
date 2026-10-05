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
    apps = {
      api = {
        image_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-api:1.0"
        routing = {
          path_pattern      = ["/api/*"]
          listener_priority = 200
        }
      }
      worker = {
        build_path = "chatbot"
        routing = {
          path_pattern      = ["/worker/*"]
          listener_priority = 300
        }
      }
    }
  }
}

run "app_map_expands_services_users_and_builds" {
  command = plan

  assert {
    condition = alltrue([
      length(module.ecs_service) == 3,
      length(mongodbatlas_database_user.ecs) == 3,
      length(module.app_infra.ecr_repositories) == 3,
      local.app_image["api"].ecr_repository_url == "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-api",
      local.app_image["api"].image_tag == "1.0",
      contains(keys(local.build_apps), "worker"),
      !contains(keys(local.build_apps), "api"),
      length(aws_codebuild_project.image) == 2,
    ])
    error_message = "A caller image_url entry should resolve to that URI and a build_path entry should get its own build"
  }
}

run "app_key_must_be_dns_safe" {
  command = plan

  variables {
    overrides = {
      apps = {
        "Bad_Key" = {
          routing = {
            path_pattern      = ["/bad/*"]
            listener_priority = 400
          }
        }
      }
    }
  }

  expect_failures = [var.overrides]
}

run "app_key_must_not_collide_with_app_name" {
  command = plan

  variables {
    overrides = {
      apps = {
        "mongodb-chatbot-demo" = {
          routing = {
            path_pattern      = ["/other/*"]
            listener_priority = 400
          }
        }
      }
    }
  }

  expect_failures = [var.overrides]
}
