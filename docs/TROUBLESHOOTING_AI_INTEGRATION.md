# Troubleshooting AI Integration (LMStudio + Supabase)

## 1. Networking (WSL2 / Linux)
**CRITICAL**: `host.docker.internal` does NOT work in this environment.
- **Problem**: Docker containers cannot find the Windows host via that alias.
- **Solution**: Use the static LAN IP of the host (e.g., `192.168.0.3`).
- **Test**: Run `docker exec -it <container_name> node -e "fetch('http://<IP>:1234/v1/models')..."` to verify connectivity.

## 2. Supabase CLI Constraints
- **Version**: 2.95.4 (and most 2.x versions)
- **Constraint**: Do NOT add custom keys like `openai_base_url` or `custom_image` directly to `supabase/config.toml`. The CLI parser will fail and stop the services.
- **Solution**: Pass these variables via `docker run -e` or a `.env` file used by a custom startup script.

## 3. Studio Patching Mechanism
- **Image**: `localhost/gamesurf/supabase-studio:lmstudio-local`
- **How it works**: It runs a script at startup (`runtime-configure-studio.js`) that performs a search-and-replace on the Next.js `.js` bundles, replacing tokens like `__GS_ENV_STUDIO_OPENAI_BASE_URL__` with the actual environment variable values.
- **Impact**: You MUST restart/recreate the container if you change environment variables; simply changing them in the OS won't update the already-patched JS bundles in the browser.

## 4. Common Error Codes
- **404 in Dashboard**: Usually means the Studio container failed to start because of a `config.toml` parse error.
- **Connection Refused (AI Chat)**: The Studio can't reach LMStudio (Check IP and Port).
- **AssertionError (EDGE_FUNCTIONS...)**: Ignore this; it's a side effect of the custom image and doesn't break the AI assistant.
