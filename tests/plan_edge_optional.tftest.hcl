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

run "worker_only_apps_create_no_edge" {
  command = plan

  variables {
    chatbot = { enabled = false }
    overrides = {
      extra_apps = {
        worker = {}
      }
    }
  }

  assert {
    condition = alltrue([
      length(local.routing_apps) == 0,
      length(module.app_infra.aws.http_edges) == 0,
      module.app_infra.https_url == null,
      output.chatbot == null,
      output.chatbot_login_password == null,
      output.https_url == null,
      length(output.extra_apps) == 1,
      output.extra_apps["worker"].path_pattern == null,
      output.extra_apps["worker"].target_group_arn == null,
      output.extra_apps["worker"].ecs_service_name == "mongodb-chatbot-demo-worker",
    ])
    error_message = "A worker-only app set should skip the ALB, CloudFront, and WAF and expose a null URL"
  }
}

run "disabled_chatbot_outputs_are_null" {
  command = plan

  variables {
    chatbot = { enabled = false }
    overrides = {
      extra_apps = {
        api = {
          routing = {
            path_pattern      = ["/api/*"]
            listener_priority = 200
          }
        }
      }
    }
  }

  assert {
    condition = alltrue([
      length(module.app_infra.aws.http_edges) == 1,
      output.chatbot == null,
      output.chatbot_login_password == null,
      startswith(output.https_url, "https://"),
      output.extra_apps["api"].path_pattern == tolist(["/api/*"]),
    ])
    error_message = "Disabling the chatbot should null its outputs and keep the edge for the routing extra app"
  }
}

run "mixed_worker_and_routing_apps_keep_per_app_paths_only" {
  command = plan

  variables {
    chatbot = { enabled = false }
    overrides = {
      extra_apps = {
        api = {
          routing = {
            path_pattern      = ["/api/*"]
            listener_priority = 200
          }
        }
        worker = {}
      }
    }
  }

  assert {
    condition = alltrue([
      length(module.app_infra.aws.http_edges) == 1,
      output.extra_apps["api"].path_pattern == tolist(["/api/*"]),
      output.extra_apps["worker"].path_pattern == null,
    ])
    error_message = "A mixed routed-plus-worker deployment should expose only the root https_url and keep per-app path data"
  }
}

run "disabled_chatbot_without_extra_apps_plans" {
  command = plan

  variables {
    chatbot = { enabled = false }
  }

  assert {
    condition = alltrue([
      length(local.apps) == 0,
      length(module.app_infra.aws.http_edges) == 0,
      output.chatbot == null,
      output.chatbot_login_password == null,
      output.https_url == null,
      length(output.extra_apps) == 0,
    ])
    error_message = "A chatbot-disabled deployment with no extra apps should plan an infra-only stack with null outputs"
  }
}

run "verify_requires_the_chatbot" {
  command = plan

  variables {
    features = { verify_deployment_ready = true }
    chatbot  = { enabled = false }
    overrides = {
      extra_apps = {
        worker = {}
      }
    }
  }

  expect_failures = [var.features]
}
