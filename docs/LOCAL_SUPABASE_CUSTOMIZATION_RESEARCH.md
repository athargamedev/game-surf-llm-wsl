# Local Supabase Customization Research

Date: 2026-05-01

## Goal

Use the local Supabase stack as a customizable, reproducible part of the Game_Surf NPC workflow, and redirect the Supabase Studio integrated AI assistant from remote OpenAI to LM Studio local models.

## Current Local State

- Game_Surf Supabase is managed by the Supabase CLI Docker stack from this repo.
- Current local endpoints from `supabase status -o env`:
  - API: `http://127.0.0.1:16433`
  - Studio: `http://127.0.0.1:16434`
  - Functions: `http://127.0.0.1:16433/functions/v1`
  - DB: `postgresql://postgres:postgres@127.0.0.1:15433/postgres`
- Storage, Imgproxy, and Pooler are stopped/excluded. They are not required for the current NPC dialogue and memory workflow.
- The NPC backend still reports `supabase_connected=true` against this stack.
- LM Studio is reachable from WSL/Docker through:
  - `http://host.docker.internal:1234/v1`
- `http://127.0.0.1:1234/v1` did not work from this WSL context, so Dockerized services should use `host.docker.internal`.

## External Source Findings

- Supabase documents `supabase/config.toml` as the local stack configuration source, and changes require `supabase stop` plus `supabase start` to take effect:
  - https://supabase.com/docs/guides/local-development/cli/config
- Supabase documents only one Studio AI config field:
  - `studio.openai_api_key`
  - It is described as the OpenAI API key used for AI features in Studio.
  - There is no documented `studio.openai_base_url` or model override.
- LM Studio documents OpenAI-compatible endpoints at `/v1/models`, `/v1/responses`, `/v1/chat/completions`, `/v1/embeddings`, and `/v1/completions`, and recommends switching OpenAI clients by changing their base URL:
  - https://lmstudio.ai/docs/developer/openai-compat
- The AI SDK OpenAI provider supports `createOpenAI({ baseURL, apiKey })`, where `baseURL` defaults to `https://api.openai.com/v1`:
  - https://ai-sdk.dev/providers/ai-sdk-providers/openai

## Local Supabase CLI Fork Findings

Local fork path:

```text
/mnt/d/GithubRepos/supabasecli
```

Important findings:

- The local CLI fork is newer than the installed CLI and includes latest Supabase stack image pins.
- The CLI fork is currently noisy/dirty on the Windows-mounted path. Before editing it, normalize file mode and line endings so real changes are reviewable.
- Studio config in `pkg/config/config.go` currently includes:
  - `enabled`
  - `image`
  - `port`
  - `api_url`
  - `openai_api_key`
  - `pgmeta_image`
- It does not include `openai_base_url`, `openai_model`, or a user-configurable Studio image field.
- `internal/start/start.go` starts the Studio container and passes `OPENAI_API_KEY`, but does not pass an OpenAI-compatible base URL or model override.
- `pkg/config/templates/config.toml` only documents `studio.openai_api_key`.
- The CLI image template pins Studio through the Supabase Studio Docker image. This means the CLI controls the container image and environment, but the assistant implementation lives inside the Studio app image.

## Key Conclusion

Redirecting the Studio AI assistant to LM Studio is not only a Supabase CLI change.

The CLI fork is useful for:

- pinning local service image versions;
- adding project-level config fields;
- passing new environment variables into Studio;
- selecting a custom Studio image;
- keeping local Supabase startup reproducible.

But the assistant behavior itself lives in the Studio image. The current CLI and documented config only provide `OPENAI_API_KEY`. To reliably use LM Studio, we need either:

1. a Studio image patch that reads local provider settings and calls an OpenAI-compatible provider with a custom base URL; or
2. a local proxy that makes Studio's existing OpenAI calls land on LM Studio and maps remote model names to local LM Studio model IDs.

The clean long-term path is a Studio image patch plus a CLI config/env patch. The proxy path is faster for a proof of concept, but it is more brittle because compiled Studio routes may use different OpenAI endpoints or hardcoded model assumptions.

## Recommended Architecture

### Source Of Truth

- Keep Game_Surf database schema, Edge Functions, and memory migrations in `LLM_WSL/supabase`.
- Keep the Supabase CLI fork in `D:\GithubRepos\supabasecli` for local stack orchestration improvements.
- Do not move Game_Surf domain migrations into the CLI fork.
- Treat the CLI fork as tooling, not application state.

### CLI Config Patch

Add support for these fields to the Studio config parser. Keep them out of the upstream default template unless the golden config diff tests are updated; Game_Surf can declare them directly in `supabase/config.toml`.

```toml
[studio]
openai_api_key = "env(OPENAI_API_KEY)"
openai_base_url = "env(STUDIO_OPENAI_BASE_URL)"
openai_model = "env(STUDIO_OPENAI_MODEL)"
openai_advanced_model = "env(STUDIO_OPENAI_ADVANCED_MODEL)"
custom_image = "localhost/gamesurf/supabase-studio:lmstudio-local"
```

Recommended default environment values for local testing:

```bash
OPENAI_API_KEY=lm-studio
STUDIO_OPENAI_BASE_URL=http://host.docker.internal:1234/v1
STUDIO_OPENAI_MODEL=qwen2.5-coder-7b-instruct
STUDIO_OPENAI_ADVANCED_MODEL=qwen3-8b
```

Pass these into the Studio container as:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
STUDIO_OPENAI_BASE_URL
STUDIO_OPENAI_MODEL
STUDIO_OPENAI_ADVANCED_MODEL
```

Passing both `OPENAI_BASE_URL` and `STUDIO_OPENAI_BASE_URL` makes the setup tolerant of whichever naming the Studio patch uses.

### Studio Patch

Patch the Studio assistant provider factory so it:

- reads `process.env.STUDIO_OPENAI_BASE_URL || process.env.OPENAI_BASE_URL`;
- reads `process.env.STUDIO_OPENAI_MODEL` for normal completions;
- reads `process.env.STUDIO_OPENAI_ADVANCED_MODEL` for advanced/coding completions;
- creates an OpenAI-compatible provider with `createOpenAI({ baseURL, apiKey })`;
- keeps remote OpenAI as the fallback when no base URL is configured.

Expected provider behavior:

```ts
const baseURL = process.env.STUDIO_OPENAI_BASE_URL || process.env.OPENAI_BASE_URL
const apiKey = process.env.OPENAI_API_KEY || 'lm-studio'
const model = process.env.STUDIO_OPENAI_MODEL || defaultModel
const provider = baseURL ? createOpenAI({ baseURL, apiKey }) : openai

return provider(model)
```

### Proxy Proof Of Concept

If Studio source patching is slow, create a local OpenAI-compatible proxy container that:

- listens on a Docker-network URL;
- exposes `/v1/models`, `/v1/chat/completions`, and `/v1/responses`;
- forwards requests to `http://host.docker.internal:1234/v1`;
- rewrites model IDs:
  - `gpt-5.4-nano` -> `qwen2.5-coder-7b-instruct`
  - `gpt-5.3-codex` -> `qwen3-8b` or `unity-coder-7b-i1`

This is a useful validation step, but the final durable implementation should still be a Studio image patch.

## Implementation Sequence

1. Normalize the CLI fork working tree.
   - Set `core.filemode=false`.
   - Confirm line-ending policy.
   - Get `git status --short` clean enough to review real changes.
2. Locate the Studio source repository or package used by the pinned Studio image.
3. Patch Studio AI provider selection for custom base URL and model env vars.
4. Build and tag a custom Studio image, for example:
   - `localhost/gamesurf/supabase-studio:lmstudio-local`
5. Patch the CLI fork:
   - add Studio config fields;
   - expose them in `config.toml`;
   - pass env vars into the Studio container;
   - allow a custom Studio image override.
6. Build a custom CLI binary from the fork.
7. Start the Game_Surf stack with the custom CLI, excluding services we do not need:
   - `storage-api`
   - `imgproxy`
   - `pooler`
8. Verify:
   - Studio loads at `http://127.0.0.1:16434`;
   - Studio AI answers through LM Studio;
   - no request goes to `api.openai.com`;
   - Game_Surf `/chat`, `/session/start`, `/session/end`, and memory tests still pass.

## Verification Commands

```bash
supabase status -o env
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker exec supabase_studio_LLM_WSL env
curl -s http://host.docker.internal:1234/v1/models
curl -s http://127.0.0.1:8000/status
```

After CLI or `supabase/config.toml` changes:

```bash
supabase stop
supabase start -x storage-api,imgproxy,pooler
```

## Risks

- The Windows-mounted CLI fork currently appears noisy. Editing before cleanup will make patch review difficult.
- Supabase Studio may have multiple AI routes. A provider patch must cover every route used by the integrated assistant.
- Some Studio AI code may call `https://api.openai.com/v1/chat/completions` directly. Those paths need explicit patching or proxy handling.
- LM Studio model compatibility varies. SQL assistant behavior should be tested with `qwen2.5-coder-7b-instruct`, `qwen3-8b`, and `unity-coder-7b-i1`.
- Supabase service images can drift quickly. Pin image tags for reproducible local tests.

## Decision

Use the CLI fork for stack orchestration and configuration, but plan on a custom Studio image for the actual LM Studio integration. The first implementation milestone should prove one Studio assistant request completes through `http://host.docker.internal:1234/v1` with a local LM Studio model and no remote OpenAI dependency.

## Implementation Snapshot

Implemented on 2026-05-01:

- Normalized `/mnt/d/GithubRepos/supabasecli` to LF working-tree files:
  - `core.autocrlf=false`
  - `core.eol=lf`
  - `core.safecrlf=warn`
- Patched the Supabase CLI fork:
  - `pkg/config/config.go` parses `studio.openai_base_url`, `studio.openai_model`, `studio.openai_advanced_model`, and `studio.custom_image`;
  - `internal/start/start.go` passes those values to the Studio container;
  - `internal/utils/docker.go` preserves explicitly registered image names such as `localhost/gamesurf/supabase-studio:lmstudio-local`;
  - `pkg/config/config_test.go` covers local Studio LLM config parsing and unset optional env values.
- Built the patched CLI binary:
  - `/mnt/d/GithubRepos/supabasecli/bin/supabase-lmstudio`
- Added Game_Surf local Studio AI config in `supabase/config.toml`:
  - `openai_api_key = "lm-studio"`
  - `openai_base_url = "http://host.docker.internal:1234/v1"`
  - `openai_model = "qwen2.5-coder-7b-instruct"`
  - `openai_advanced_model = "qwen3-8b"`
  - `custom_image = "localhost/gamesurf/supabase-studio:lmstudio-local"`
- Added the derived Studio image patch:
  - `docker/supabase-studio-lmstudio/Dockerfile`
  - `docker/supabase-studio-lmstudio/patch-studio-lmstudio.js`
- Built the patched Studio image:
  - `localhost/gamesurf/supabase-studio:lmstudio-local`
- Added a helper start script:
  - `scripts/start_supabase_lmstudio.sh`

Verification:

- `docker ps` shows `supabase_studio_LLM_WSL` running `localhost/gamesurf/supabase-studio:lmstudio-local`.
- `docker exec supabase_studio_LLM_WSL env` shows:
  - `OPENAI_API_KEY=lm-studio`
  - `OPENAI_BASE_URL=http://host.docker.internal:1234/v1`
  - `STUDIO_OPENAI_BASE_URL=http://host.docker.internal:1234/v1`
  - `STUDIO_OPENAI_MODEL=qwen2.5-coder-7b-instruct`
  - `STUDIO_OPENAI_ADVANCED_MODEL=qwen3-8b`
- The Studio SQL assistant endpoint `/api/ai/sql/generate-v4` returned `200 OK` as a text/event-stream through the local provider.
- Structured-output helper routes such as feedback classification and SQL title generation still need prompt/model tuning because the local model response was not parseable as the object schema Studio expects.

Known test status:

- Passed:
  - `go test ./internal/start`
  - `go test ./config -run 'TestConfigParsing/(studio local llm config|optional studio env config clears unset env values)'`
- Not clean:
  - `go test ./internal/utils` has pre-existing WSL/keyring and mocked Docker API failures unrelated to this patch.
