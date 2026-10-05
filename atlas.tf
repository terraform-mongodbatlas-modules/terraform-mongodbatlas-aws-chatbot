# Atlas: project, AWS integration (PrivateLink, KMS, log and backup export),
# cluster, and database users. The published modules are composed here so the
# wiring is readable.

data "mongodbatlas_roles_org_id" "current" {}

# --- Debug access -------------------------------------------------------------
# `features.debug_access_for_cluster` adds the caller IP to the project access
# list and creates a SCRAM database user. `overrides.allowed_ip` overrides the
# resolved address; an empty value resolves the caller's public IP at apply.
data "http" "caller_ip" {
  count = var.features.debug_access_for_cluster && var.overrides.allowed_ip == "" ? 1 : 0
  url   = "https://checkip.amazonaws.com/"
}

locals {
  debug_ip = var.features.debug_access_for_cluster ? (
    var.overrides.allowed_ip != "" ? var.overrides.allowed_ip : trimspace(data.http.caller_ip[0].response_body)
  ) : null

  public_debug_connection_string = var.features.debug_access_for_cluster ? format(
    "mongodb+srv://%s:%s@%s/?authSource=admin",
    urlencode("debug"),
    urlencode(random_password.public_debug[0].result),
    trimprefix(module.atlas_cluster.connection_strings.standard_srv, "mongodb+srv://")
  ) : null
}

resource "random_password" "public_debug" {
  count   = var.features.debug_access_for_cluster ? 1 : 0
  length  = 24
  special = false
}

resource "mongodbatlas_database_user" "public_debug" {
  count = var.features.debug_access_for_cluster ? 1 : 0

  project_id         = module.atlas_project.id
  username           = "debug"
  password           = random_password.public_debug[0].result
  auth_database_name = "admin"

  roles {
    role_name     = local.debug_db_access.role_name
    database_name = local.debug_db_access.database_name
  }

  depends_on = [module.atlas_cluster]
}

# --- Atlas project and AWS integration ---------------------------------------

module "atlas_project" {
  source  = "terraform-mongodbatlas-modules/project/mongodbatlas"
  version = "~> 0.2"

  org_id = local.atlas_org_id
  name   = var.app_name
  tags   = local.tags
  ip_access_list = var.features.debug_access_for_cluster ? [
    {
      source  = local.debug_ip
      comment = "debug access"
    }
  ] : []
}

module "atlas_aws" {
  source  = "terraform-mongodbatlas-modules/atlas-aws/mongodbatlas"
  version = "~> 0.4"

  project_id = module.atlas_project.id

  # PrivateLink into the app infra VPC. module.app_infra must come first: these
  # are its subnet IDs.
  privatelink_endpoints = [
    for r in local.regions_resolved : {
      region     = r.atlas_name
      subnet_ids = module.app_infra.region_network[r.aws_name].private_subnet_ids
      security_group = {
        inbound_cidr_blocks = [module.app_infra.region_network[r.aws_name].vpc_cidr_block]
      }
    }
  ]

  encryption      = local.atlas_aws_encryption
  log_integration = local.atlas_aws_log_integration
  backup_export   = local.atlas_aws_backup_export

  aws_tags = local.tags
}

module "atlas_cluster" {
  source  = "terraform-mongodbatlas-modules/cluster/mongodbatlas"
  version = "~> 0.4"

  project_id    = module.atlas_project.id
  name          = var.app_name
  provider_name = "AWS"
  cluster_type  = var.overrides.cluster.cluster_type
  shard_count   = var.overrides.cluster.cluster_type == "SHARDED" ? var.overrides.cluster.shard_count : null

  regions                     = local.cluster_regions
  instance_size               = local.cluster_instance_size
  auto_scaling                = local.cluster_auto_scaling
  version_release_system      = "CONTINUOUS"
  encryption_at_rest_provider = module.atlas_aws.encryption_at_rest_provider
  tags                        = local.tags

  # No `depends_on = [module.atlas_aws]`. `encryption_at_rest_provider` already
  # orders the cluster after the project's encryption-at-rest configuration, and
  # CLOUDP-452488 makes the connection string a data source that reads after both the
  # cluster and the PrivateLink endpoint exist.
}

# --- Database users -----------------------------------------------------------

# One IAM database user per ECS app. Username is the task role ARN, so the
# container authenticates with MONGODB-AWS and no password.
resource "mongodbatlas_database_user" "ecs" {
  for_each = local.ecs_apps

  project_id         = module.atlas_project.id
  username           = module.app_infra.aws.ecs_task_roles[each.key]
  auth_database_name = "$external"
  aws_iam_type       = "ROLE"

  dynamic "roles" {
    for_each = each.value.roles

    content {
      role_name       = roles.value.role_name
      database_name   = roles.value.database_name
      collection_name = roles.value.collection_name
    }
  }

  depends_on = [module.atlas_cluster]
}

# --- PrivateLink wiring -------------------------------------------------------

# Atlas PrivateLink endpoint SG accepts 1024-65535 from the app SG. The endpoint
# and the app SG are created by different modules, so the rule lives here.
resource "aws_security_group_rule" "atlas_pl_ingress_from_app" {
  for_each = local.app_aws_regions

  region                   = each.key
  type                     = "ingress"
  from_port                = 1024
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = module.atlas_aws.privatelink[each.key].security_group_id
  source_security_group_id = module.app_infra.aws.compute[each.key].app_security_group_id
  description              = "MongoDB Atlas PrivateLink from app SG"
}
