# Make it your own

This guide is experimental. It covers inputs and workflows that the examples do not exercise yet, so the shape may change. The [minimal example](../examples/minimal) and the input reference in the [README](../README.md) are the tested path.

## Content

- **`queries`:** the starter questions, an ordered list of `{ label, message }` objects. Each `label` is the chip shown in the UI and each `message` is the question it sends. The chips appear in list order. Empty keeps the app's bundled questions. At startup the task writes the list into the default profile document in `_chatbot_profiles`, which is what the app reads.
- **`document_dirs`:** the documents to ingest. A bare name resolves to the bundled corpus; a path or an absolute path is used as-is.
- **`assets_dir`:** a directory mirroring the app's `assets/` tree, copied over the rendered defaults. Replace `.chainlit/config.toml`, `chainlit.md`, and `public/` to rebrand.
- **`chatbot.system_prompt`:** the RAG system prompt the app answers with. At startup the task writes it into the default profile document in `_chatbot_profiles`.
- **`chatbot.llm_max_snippets`:** how many of the retrieved chunks the model reads for each answer. The app default is 5 and the search returns 20.
- **`chatbot.llm_history_turns`:** how many earlier turns of the chat the model sees with each new question, so a follow-up can refer back. The app default is 10; 0 turns it off, and with it the follow-up rewriting.
- **`chatbot.rewrite_followups`:** whether the model restates a follow-up as a standalone question before the search runs. The app default is true. It costs one extra model call per follow-up and none on the first message of a chat. A user can flip it per session with the **Rewrite follow-ups** switch in the chat settings.
- **`chatbot.rerank_results`, `chatbot.rerank_candidates`:** reorder the retrieved candidates with Atlas native reranking (`$rerank`) before the answer. Off by default: the cluster needs MongoDB 9.0 or later, and Native Reranking has to be enabled in the Atlas project settings. When on, the chat gets a **Rerank results** switch. The app reads 80 candidates by default.

## The app

- **`chatbot.container_size`, `chatbot.task_cpu`, `chatbot.task_memory`:** the ECS task size.
- **`chatbot.image_url` or `chatbot.dockerfile_path`:** bring your own image, or build your own Dockerfile instead of the vendored app. The two are mutually exclusive.
- **`overrides.extra_apps`:** more apps on the same cluster. An entry with `routing` joins the shared edge; an entry with no `routing` is a private worker with no HTTP edge.

## The LLM

The default is Amazon Bedrock, which uses the task role and needs no key. For a keyed provider, create the secret with `just create-llm-secret`, then set `llm.provider` and `llm.secret_name`. Grove also needs `llm.base_url`. Set `llm.model` to pin the model.

## Run the app locally

Apply with `features.debug_access_for_cluster = true`, then run `just dump-local-env` from your Terraform workspace. It writes `secrets/.env.local` from the deployed app secret and prints the docker compose command, so you can iterate on the app and `assets_dir` without a full apply. The file carries `chatbot.system_prompt` as `RAG_SYSTEM_PROMPT`, so the local default profile answers with the deployment's prompt. A deployment without that input leaves the key out, and the app keeps its built-in prompt.

## Reach the internals

- **`overrides.project_id`:** deploy into an existing Atlas project instead of creating one. The project module runs in reference mode: the module does not create, rename, or tag the project and does not read the organization, so a project-scoped credential is enough. The module still manages the project's access list for debug access.
- **`overrides.byo_vpc`:** a per-region map that replaces the managed VPC. A BYO VPC that serves the HTTP edge must already have an internet gateway, because CloudFront reaches the load balancer through a VPC origin.
- **`overrides.cluster`:** the cluster type, shard count, instance size, and the Automated Embedding model. `advanced_configuration` is passed to the cluster module unchanged, so its fields are the same as the cluster module's and are documented in the [cluster module reference](https://registry.terraform.io/modules/terraform-mongodbatlas-modules/cluster/mongodbatlas/latest). `redact_client_log_data` defaults to `true`; set it to `false` to keep query filters in the cluster logs for the Query Profiler and Performance Advisor. Changing it triggers a rolling restart.
- **`overrides.domain`:** the custom-domain aliases and the ACM certificate.
- **`overrides.allowed_ip`:** a fixed debug IP instead of resolving the caller's.
- **`overrides.networking`:** the shared edge settings, for example `waf_disabled`.
- **`overrides.skip_tags`:** set no tags at all.

## Demo questions by persona

Tailor the starter questions to your audience. For example, a developer or platform engineer, an applied AI engineer, a founder or CTO, a VP or security reviewer, a data engineer coming from Postgres and a vector store, or a pre-sales SA. Pick a persona from the list below, or write your own.

The bundled corpus answers the MongoDB questions ("Why one database", "Why not Postgres", "Hybrid ranking", "Agent memory", "Embedding freshness") and the deployment question ("Security posture"). The "Make it your own" question returns a generic answer from this guide's bundled copy. A question about your own product needs your documents, so add them with `document_dirs`.

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

The chips appear in list order. Reorder or drop entries to fit your audience.

## A second corpus in one deployment

One deployment can serve more than one corpus. Each corpus is a chunks collection in `MONGODB_DATABASE`, and the visitor picks one from the chat profile dropdown on the start screen. The default collection keeps the bundled corpus. Registering another collection adds a profile next to it.

### The profile registry

The `_chatbot_profiles` collection holds one document per selectable chunks collection, and the document's `_id` is that collection's name. A collection is selectable only when the registry holds a document for it, so the registry doubles as the allowlist. The configured default collection is always selectable, even before its document exists, and falls back to the bundled questions and `RAG_SYSTEM_PROMPT`.

Because the profiles live in their own collection, a chunks collection holds only chunks. Search never returns a profile, and "Delete all" never deletes one.

A profile document carries:

- **`display_name`:** the label in the dropdown.
- **`description`:** the tooltip under the label.
- **`icon`:** an image URL the app serves, for example `/public/logo_light.svg`.
- **`queries`:** the starter chips, an ordered list of `{ label, message }`.
- **`system_prompt`:** the answer prompt for this corpus.

The startup task writes the default collection's document from `queries` and `chatbot.system_prompt`. It sets `display_name` only when it creates the document, so a label you registered survives a restart. A profile without `system_prompt` answers with the module's `RAG_SYSTEM_PROMPT`. The default profile without `queries` shows the bundled questions, and another profile without `queries` shows only the upload and delete starters.

### The corpus directory

A corpus is a directory that describes itself in `corpus.yaml`:

- **`collection`:** the chunks collection to create or update. It must start with a letter or digit and use only letters, digits, underscores, and hyphens.
- **`display_name`:** the label in the dropdown.
- **`description`, `icon`:** optional tooltip text and an image URL the app serves.
- **`queries`, `system_prompt`, `docs`:** optional paths. When a field is omitted, the loader uses `queries.yaml`, `system_prompt.txt`, and `docs/` beside the manifest when they exist.

The directory names itself, so adding another bundled corpus is: copy the directory, edit `corpus.yaml`, and run the recipe. `examples/healthcare` is one; its file names are the omitted-field defaults.

### Register a collection

Register the corpus directory against the deployed database. The local UI section writes `secrets/.env.local`, and that file carries `MONGODB_URI`.

```sh
just dump-local-env terraform_dir=<your terraform workspace>
just register-corpus examples/healthcare
```

`dump-local-env` reads an existing deployment's state, so registering a second corpus needs no new apply. The recipe writes the profile document in `_chatbot_profiles`, creates the collection's search indexes, and ingests `docs/` into `healthcare_ingest_state`. For a corpus without a manifest, run the CLI directly:

```sh
cd chatbot
set -a; . secrets/.env.local; set +a
uv run --extra ui hybrid-search register \
  --collection healthcare \
  --display-name "Springfield Health" \
  --description "Fictional member-services corpus with four family personas" \
  --demo-queries ../examples/healthcare/queries.yaml \
  --system-prompt ../examples/healthcare/system_prompt.txt \
  --dir ../examples/healthcare/docs
```

The command creates the two Atlas search indexes on the collection, writes the profile document in `_chatbot_profiles`, and ingests the directory into a per-collection ingest state (`healthcare_ingest_state`). `--demo-queries`, `--system-prompt`, and `--dir` are optional. Omitting a file keeps whatever the document already held, and omitting `--dir` skips ingest.

The collection name must start with a letter or digit and use only letters, digits, underscores, and hyphens. The registry's own name starts with an underscore, so it can never be registered or selected.

### Pick the corpus

Reload the app and choose the profile on the start screen. The selector appears only when more than one collection is registered, so a single-corpus deployment looks the same as before. The server caches the listing for 30 seconds, so a registration can take a page reload or two to appear.

The database user needs the module's default database-wide `readWrite` grant to read `_chatbot_profiles` and every registered collection. Setting `db_access.collection_name` narrows the user to one collection, so the app cannot read the registry and shows only the default profile.

To rename the default profile, register the default collection with a label. The startup write only sets the label when it creates the document, so the name persists.

```sh
uv run --extra ui hybrid-search register --collection chunks --display-name "Product docs"
```

## Landing Zone modules

The module composes the published [project](https://registry.terraform.io/modules/terraform-mongodbatlas-modules/project/mongodbatlas/latest), [cluster](https://registry.terraform.io/modules/terraform-mongodbatlas-modules/cluster/mongodbatlas/latest), and [atlas-aws](https://registry.terraform.io/modules/terraform-mongodbatlas-modules/atlas-aws/mongodbatlas/latest) modules. Their full schemas live in the Terraform registry.

## Feedback

This guide is a starting point, not a tested path. Open a GitHub issue if something here does not work.
