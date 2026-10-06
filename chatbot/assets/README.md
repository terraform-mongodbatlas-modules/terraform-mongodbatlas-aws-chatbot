# Assets

Files a user of this example edits. The image copies this whole directory to
`/app/assets`, and Chainlit reads its config and welcome file from here.

- **`.chainlit/config.toml`**: UI name, description, language, and `cot`. The
  browser tab title is `[UI] name`.
- **`chainlit.md`**: Header Readme dialog content. `chainlit_en-US.md` is a symlink to it,
  read for the configured `en-US` language. Chainlit logs a warning on every
  page load when the language has no file.
- **`public/`**: MongoDB brand assets. Chainlit serves them automatically:
  `logo_light.svg`, `logo_dark.svg`, and `favicon.svg` for the header and tab,
  and `theme.css` for the brand palette (`custom_css` in `.chainlit/config.toml`
  points at it). Replace these to rebrand a fork.
- **`.chainlit/translations/`** and **`.files/`**: Not committed. Chainlit
  creates them on first run from its packaged defaults.
- **`demo_queries.yaml`**: Starter chips and the Demo picker. `label` is the chip
  text, `message` is the query.
- **`document_dirs/`**: Ingest corpus, and the `DOCUMENT_DIRS` default. Ships a
  short "why MongoDB for agents" write-up, so a fresh deploy is queryable with no
  upload. The module replaces this directory with the caller's `document_dirs`.

The app reads `demo_queries.yaml` from `assets/demo_queries.yaml` by default
(`DEMO_QUERIES_PATH` overrides it). In the pattern module the whole directory is
rendered per apply, so a change to any file here rebuilds the image.
