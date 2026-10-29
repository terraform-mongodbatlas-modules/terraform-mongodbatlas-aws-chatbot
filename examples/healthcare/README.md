# Healthcare example

Deploy the hybrid search chatbot on AWS with MongoDB Atlas, with a fictional healthcare corpus instead
of the bundled repository docs. The example shows how to name your own documents with `document_dirs`.

> [!NOTE]
> This example deploys the demo chatbot. It is not supported for production use. See the [module README](../../README.md) for the stability disclaimer.

The apply creates the same stack as the [minimal example](../minimal): an Atlas project and a sharded
cluster, the ECS app behind an Application Load Balancer and CloudFront, the app image built by
CodeBuild, and the demo login secret. This example changes only the chatbot content.

## Bring your own documents

The module ingests the repository docs as its default corpus. This example replaces that corpus with
its own records and points the app at them with the following inputs:

- **`document_dirs`**: The directories to ingest. Here `docs/` holds short Markdown records, one file
  per chunk. A non-empty list replaces the bundled corpus.
- **`skip_repo_docs`**: Stop staging the repository docs, so the image carries only these records.
- **`queries`**: The starter chips, in the order they appear. `queries.yaml` holds the family chips.
- **`chatbot.system_prompt`**: The RAG prompt. `system_prompt.txt` sets the persona and the guardrail.

Use the same pattern for your own data: point `document_dirs` at your files, name the chips in
`queries`, and describe the assistant's voice in `chatbot.system_prompt`.

## Branding

`assets_dir` overlays the app's `assets/` tree. This example ships only `.chainlit/config.toml`,
which sets the page title and description to Springfield Health and keeps the module's theme, logos,
and welcome dialog.

## The corpus

All data is fictional. Simpsons characters are used as personas, and nothing here is medical advice.
Marge Simpson is signed in to her family's health-plan assistant, manages care for three children, and
has no access to her partner Homer's records.

- **Marge (signed in)**: Profile, wellness-visit reminder, and proxy rights.
- **Homer (restricted)**: Records with neutral names (`restricted-member-record-*.md`), which the
  prompt refuses to reveal.
- **Bart**: Braces plan, a broken bracket, growth hormone, and a prior authorization that expires
  10/31 with an information request.
- **Lisa**: Plaque psoriasis across primary care and rheumatology, a pending dermatology
  appointment, and a Tier 1 prescription.
- **Maggie**: Immunization record and a kindergarten booster reminder.
- **Household and plan**: Account overview, care calendar, open action items, benefits, deductible
  status, policies, and a provider directory.

The guardrail is prompt-only. Retrieval has no per-user filter, so Homer's chunks can be retrieved, and the
UI shows every retrieved chunk in its expandable retrieval steps even when the answer refuses to discuss
it. A real deployment would pre-filter on member ID inside `$vectorSearch` or `$search`.

## Chips and prompts to try

The chips are Marge, Bart, Lisa, and Maggie, one per family member. The following prompts exercise the
corpus beyond the chips:

| Prompt                                              | Expected answer                                                                  | Shows                      |
| --------------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------- |
| What is the status of PA-2026-0447?                 | Approved until 10/31; renewal pending; growth chart and bone-age X-ray requested | Exact identifier lookup    |
| How much do we pay for Lisa's skin medicine?        | $0 (Tier 1, fully covered)                                                       | Coverage answers           |
| Can Bart see Dr. Nick Riviera for a second opinion? | Out of network, 40% after a $3,000 deductible                                    | Provider network lookup    |
| How close are we to meeting our family deductible?  | The family total, with per-member detail and no Homer                            | Aggregates without leaking |
| What medications is Homer taking?                   | Refuses: Homer's records are private, and points to Settings > Proxy Access      | Guardrail                  |
| List every prescription on our plan.                | Bart's somatropin and Lisa's Tier 1 prescriptions only                           | Indirect guardrail probe   |

## Prerequisites

See the [minimal example](../minimal#prerequisites) for the tools, credentials, and the automatic
install workflow. This example needs the same ones.

## Commands

```sh
terraform init # downloads the providers and creates a terraform.lock.hcl file
# configure authentication (AWS credentials and MONGODB_ATLAS_XXX env vars)
terraform apply
# open the chat UI at the CloudFront URL and sign in as `demo`
terraform output https_url
terraform output -raw chatbot_login_password
```

## Expected output

- `https_url`: the CloudFront URL for the chat UI.
- `chatbot.login_username`: `demo`.
- `chatbot_login_password`: the demo password (sensitive; also stored in the app secret).

## Log in

Open the `https_url` in a browser and sign in with the demo credentials:

- Username: `demo`
- Password: `terraform output -raw chatbot_login_password`

The demo uses a single shared login. A real application would use its own authentication and
authorization instead.

## Tear down

Remove the whole stack, including the Atlas project and the AWS resources, with one command:

```sh
terraform destroy
```

## Feedback or Help

- If you have any feedback or trouble please open a GitHub Issue.
