## (Unreleased)

NOTES:

* module: Documents why a small input change replaces the app secret version and the ECS task definition ([#26](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/26))

ENHANCEMENTS:

* module: Adds `overrides.project_id` to deploy into an existing Atlas project and `overrides.cluster.advanced_configuration` to pass the cluster's advanced settings through ([#29](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/29))
* module: Answers only from the retrieved context in the bundled chatbot app and declines when the context is insufficient ([#26](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/26))
* module: Shows each retrieved chunk as its own collapsed step in the chat app, so a viewer opens only the chunk they need ([#26](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/26))

BUG FIXES:

* module: Renders retrieved chunk previews in a code fence so fenced blocks and image references no longer break the chat app output ([#26](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/26))
* module: Shortens plan snapshot paths so Windows can clone the module without exceeding the path length limit ([#25](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/25))

## 0.1.0 (October 19, 2026)

NOTES:

* module: Adds the vendored hybrid-search chatbot app at chatbot/ with unit and integration test tiers ([#2](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/2))
* module: Composes the Atlas, app infrastructure, and CodeBuild image pipeline into one root-module deployment ([#3](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/3))
* module: Documents the captured least-privilege deployer policy and the permissions boundary ([#12](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/12))
* module: Documents the module and assembles the bundled corpus from the repository docs ([#6](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/6))

ENHANCEMENTS:

* example: Adds the minimal single-file deployment example ([#6](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/6))
* module: Adds `overrides.permissions_boundary`, applied to every IAM role the module creates ([#12](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/12))
* module: Adds per-app runtime handles and database access to the chatbot and extra_apps outputs ([#3](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/3))
* module: Creates the CodeBuild CloudWatch log group so `terraform destroy` removes it ([#12](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/12))
* module: Keeps the demo starter questions in list order and bundles the make-it-your-own guide ([#6](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/6))
* module: Tags every resource the module creates, including the build resources and the edge listener and rule ([#12](https://github.com/terraform-mongodbatlas-modules/terraform-mongodbatlas-aws-chatbot/pull/12))
