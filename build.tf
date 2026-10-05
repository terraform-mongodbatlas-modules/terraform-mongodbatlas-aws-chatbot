# Image build. Two archive_file sources feed CodeBuild: the vendored app tree is
# the primary source and the module-rendered assets tree is a secondary source.
# A start-and-poll script waits for the build and fails the apply on a failed
# status.

data "aws_caller_identity" "current" {}

locals {
  # Per-app content-addressed tag. A change to the app tree or (for the
  # chatbot) the assets tree moves the tag and starts one build; ECR is
  # IMMUTABLE, so unchanged source reuses the tag.
  image_tags = {
    for k, app in local.build_apps : k => (
      k == "chatbot"
      ? "sha-${substr(sha256("${data.archive_file.app[k].output_base64sha256}:${local.assets_content_hash}"), 0, 12)}"
      : "sha-${substr(sha256(data.archive_file.app[k].output_base64sha256), 0, 12)}"
    )
  }

  build_enabled = length(local.build_apps) > 0
  chatbot_built = contains(keys(local.build_apps), "chatbot")

  # Excludes for the app source zip. The pattern list lives in
  # chatbot/.archiveignore so it can be read and edited as a file; blank lines
  # and `#` comments are dropped here.
  archive_excludes = compact([
    for line in split("\n", file("${path.module}/chatbot/.archiveignore")) :
    trimspace(line)
    if trimspace(line) != "" && !startswith(trimspace(line), "#")
  ])

  # Change detector for the vendored assets tree, so a new default re-renders
  # the staging tree even when the caller's inputs are unchanged.
  vendored_assets_hash = sha256(join("", [
    for f in sort(fileset("${path.module}/chatbot/assets", "**")) :
    filesha256("${path.module}/chatbot/assets/${f}")
  ]))

  # Content hash of everything the assets tree render consumes. `data.archive_file
  # .assets` defers to apply on the first run (it depends on the render), so the
  # image tag hashes this plan-known value instead of the zip, which keeps the
  # tag readable at plan while still moving on any content change.
  assets_override_file_hashes = concat(
    var.assets_dir == null ? [] : [
      for f in fileset(var.assets_dir, "**") : filesha256("${var.assets_dir}/${f}")
    ],
    flatten([
      for entry in var.document_dirs :
      try([for f in fileset(entry, "**") : filesha256("${entry}/${f}")], [filesha256(entry)])
    ]),
  )
  assets_content_hash = sha256(jsonencode({
    vendored       = local.vendored_assets_hash
    queries        = var.queries
    override_files = local.assets_override_file_hashes
  }))
}

# --- App source archives ------------------------------------------------------

data "archive_file" "app" {
  for_each = local.build_apps

  type        = "zip"
  source_dir  = coalesce(each.value.build_path, "${path.module}/chatbot")
  output_path = "${path.module}/.build/${each.key}/app.zip"

  # The vendored tree carries local build state on disk; without excludes the
  # zip is huge and non-deterministic. Patterns live in chatbot/.archiveignore.
  excludes = local.archive_excludes
}

# --- Assets tree render -------------------------------------------------------
# One rendered tree carries every user-configurable file. The script assembles
# the vendored defaults, renders `queries` and `document_dirs`, and overlays
# `assets_dir`, so the tree is always complete.

resource "terraform_data" "render_assets" {
  count = local.chatbot_built ? 1 : 0

  triggers_replace = {
    queries              = var.queries
    document_dirs        = var.document_dirs
    assets_dir           = var.assets_dir
    vendored_assets_hash = local.vendored_assets_hash
  }

  provisioner "local-exec" {
    command = join(" ", [
      "python3 ${path.module}/scripts/render_assets.py",
      "--module-dir ${path.module}",
      "--staging-dir ${path.module}/.render/assets",
      "--queries-b64 ${base64encode(jsonencode(var.queries))}",
      "--document-dirs-b64 ${base64encode(jsonencode(var.document_dirs))}",
      "--assets-dir \"${coalesce(var.assets_dir, "")}\"",
    ])
  }
}

data "archive_file" "assets" {
  count = local.chatbot_built ? 1 : 0

  type        = "zip"
  source_dir  = "${path.module}/.render/assets"
  output_path = "${path.module}/.build/assets.zip"

  # The read defers to apply on the first run, after the render creates the tree.
  depends_on = [terraform_data.render_assets]
}

# --- Source bucket ------------------------------------------------------------

resource "aws_s3_bucket" "source" {
  count = local.build_enabled ? 1 : 0

  region        = local.aws_region
  bucket_prefix = "${var.app_name}-codebuild-"
  force_destroy = true
}

resource "aws_s3_object" "app" {
  for_each = local.build_apps

  region      = local.aws_region
  bucket      = aws_s3_bucket.source[0].id
  key         = "${each.key}/app.zip"
  source      = data.archive_file.app[each.key].output_path
  source_hash = data.archive_file.app[each.key].output_base64sha256
}

resource "aws_s3_object" "assets" {
  count = local.chatbot_built ? 1 : 0

  region      = local.aws_region
  bucket      = aws_s3_bucket.source[0].id
  key         = "assets.zip"
  source      = data.archive_file.assets[0].output_path
  source_hash = data.archive_file.assets[0].output_base64sha256
}

# --- Build IAM ----------------------------------------------------------------

data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  count = local.build_enabled ? 1 : 0

  name               = "${var.app_name}-codebuild"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json
}

data "aws_iam_policy_document" "codebuild" {
  count = local.build_enabled ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = ["${aws_s3_bucket.source[0].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      for k, app in local.build_apps :
      "arn:aws:ecr:${app.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${app.name}"
    ]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  count = local.build_enabled ? 1 : 0

  name   = "${var.app_name}-codebuild"
  role   = aws_iam_role.codebuild[0].id
  policy = data.aws_iam_policy_document.codebuild[0].json
}

# IAM policy changes are eventually consistent. CodeBuild creates the build's
# log stream on the first build, and a policy attached in the same apply can
# lose that race, failing the build with logs:CreateLogStream denied.
resource "time_sleep" "iam_propagation" {
  count = local.build_enabled ? 1 : 0

  depends_on = [aws_iam_role_policy.codebuild]

  triggers = {
    policy = aws_iam_role_policy.codebuild[0].policy
  }

  create_duration = "10s"
}

# --- CodeBuild project --------------------------------------------------------

resource "aws_codebuild_project" "image" {
  for_each = local.build_apps

  region           = each.value.aws_region
  name             = "${each.value.name}-image"
  service_role     = aws_iam_role.codebuild[0].arn
  build_timeout    = 20
  queued_timeout   = 10
  auto_retry_limit = 2

  depends_on = [time_sleep.iam_propagation]

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type  = "LOCAL"
    modes = ["LOCAL_DOCKER_LAYER_CACHE", "LOCAL_SOURCE_CACHE"]
  }

  environment {
    type            = "ARM_CONTAINER"
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/amazonlinux2-aarch64-standard:3.0"
    privileged_mode = true
  }

  # Primary source: the app tree. CodeBuild extracts it to CODEBUILD_SRC_DIR.
  source {
    type     = "S3"
    location = "${aws_s3_object.app[each.key].bucket}/${aws_s3_object.app[each.key].key}"
    buildspec = templatefile("${path.module}/buildspec.yaml", {
      ecr_repo_url = module.app_infra.ecs_apps[each.key].ecr_repository_url
      has_assets   = each.key == "chatbot"
    })
  }

  # Secondary source: the rendered assets tree, only for the vendored app.
  dynamic "secondary_sources" {
    for_each = each.key == "chatbot" ? [1] : []
    content {
      source_identifier = "assets"
      type              = "S3"
      location          = "${aws_s3_object.assets[0].bucket}/${aws_s3_object.assets[0].key}"
    }
  }
}

# --- Start and poll -----------------------------------------------------------

resource "terraform_data" "build" {
  for_each = local.build_apps

  triggers_replace = [local.image_tags[each.key]]

  depends_on = [aws_codebuild_project.image]

  provisioner "local-exec" {
    command = join(" ", [
      "python3 ${path.module}/scripts/start_build.py",
      "--project ${aws_codebuild_project.image[each.key].name}",
      "--tag ${local.image_tags[each.key]}",
      "--ecr-repo ${each.value.name}",
      "--region ${each.value.aws_region}",
      "--out ${path.module}/.build/${each.key}/build.json",
    ])
  }
}

data "local_file" "build_info" {
  for_each = local.build_apps

  filename   = "${path.module}/.build/${each.key}/build.json"
  depends_on = [terraform_data.build]
}
