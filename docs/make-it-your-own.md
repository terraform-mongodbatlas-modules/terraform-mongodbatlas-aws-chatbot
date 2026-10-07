# Make it your own

This guide is experimental. It covers inputs and workflows that the examples do not exercise yet, so the shape may change. The [minimal example](../examples/minimal) and the input reference in the [README](../README.md) are the tested path.

## Content

- **`queries`:** the starter questions, an ordered list of `{ label, message }` objects. Each `label` is the chip shown in the UI and each `message` is the question it sends. The chips appear in list order. Empty keeps the app's bundled questions.
- **`document_dirs`:** the documents to ingest. A bare name resolves to the bundled corpus; a path or an absolute path is used as-is.
- **`assets_dir`:** a directory mirroring the app's `assets/` tree, copied over the rendered defaults. Replace `.chainlit/config.toml`, `chainlit.md`, and `public/` to rebrand.
- **`chatbot.system_prompt`:** the RAG system prompt the app answers with.

## The app

- **`chatbot.container_size`, `chatbot.task_cpu`, `chatbot.task_memory`:** the ECS task size.
- **`chatbot.image_url` or `chatbot.dockerfile_path`:** bring your own image, or build your own Dockerfile instead of the vendored app. The two are mutually exclusive.
- **`overrides.extra_apps`:** more apps on the same cluster. An entry with `routing` joins the shared edge; an entry with no `routing` is a private worker with no HTTP edge.

## The LLM

The default is Amazon Bedrock, which uses the task role and needs no key. For a keyed provider, create the secret with `just create-llm-secret`, then set `llm.provider` and `llm.secret_name`. Grove also needs `llm.base_url`. Set `llm.model` to pin the model.

## Run the app locally

Apply with `features.debug_access_for_cluster = true`, then run `just dump-local-env` from your Terraform workspace. It writes `secrets/.env.local` from the deployed app secret and prints the docker compose command, so you can iterate on the app and `assets_dir` without a full apply.

## Reach the internals

- **`overrides.byo_vpc`:** a per-region map that replaces the managed VPC. A BYO VPC that serves the HTTP edge must already have an internet gateway, because CloudFront reaches the load balancer through a VPC origin.
- **`overrides.cluster`:** the cluster type, shard count, instance size, and the Automated Embedding model.
- **`overrides.domain`:** the custom-domain aliases and the ACM certificate.
- **`overrides.allowed_ip`:** a fixed debug IP instead of resolving the caller's.
- **`overrides.networking`:** the shared edge settings, for example `waf_disabled`.
- **`overrides.skip_tags`:** set no tags at all.

## Demo questions by persona

Tailor the starter set to who is in the room: a developer or platform engineer, an applied AI engineer, a founder or CTO, a VP or security reviewer, a data engineer coming from Postgres and a vector store, or a pre-sales SA. Pick from the list below, or write your own.

The bundled corpus answers the MongoDB questions (Why one database, Why not Postgres, Hybrid ranking, Agent memory, Embedding freshness) and the deployment question (Security posture). Make it your own answers generically from this guide's bundled copy. A question about your own product needs your documents, so add them with `document_dirs`.

```hcl
queries = [
  { label = "Why one database", message = "Why would an agent store retrieval and memory in the same database instead of a separate vector store?" },
  { label = "Why not Postgres", message = "Why would an agent use MongoDB instead of a relational database like PostgreSQL?" },
  { label = "Hybrid ranking", message = "How does $rankFusion combine keyword and vector search results?" },
  { label = "Agent memory", message = "How do I store short-term and long-term memory for an agent in MongoDB?" },
  { label = "Embedding freshness", message = "How does Automated Embedding keep vectors in sync when the underlying document changes?" },
  { label = "Security posture", message = "What network and IAM controls does this deployment use?" },
  { label = "Make it your own", message = "How do I make this demo my own?" },
]
```

The chips appear in list order. Reorder or drop entries to fit the audience.

## Landing Zone modules

The module composes the published [project](https://registry.terraform.io/modules/terraform-mongodbatlas-modules/project/mongodbatlas/latest), [cluster](https://registry.terraform.io/modules/terraform-mongodbatlas-modules/cluster/mongodbatlas/latest), and [atlas-aws](https://registry.terraform.io/modules/terraform-mongodbatlas-modules/atlas-aws/mongodbatlas/latest) modules. Their full schemas live in the registry.

## Feedback

This guide is a starting point, not a tested path. Open a GitHub issue if something here does not work.
