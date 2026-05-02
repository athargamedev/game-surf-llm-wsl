const fs = require("fs")
const path = require("path")

const bundleRoots = [
  "/app/apps/studio/.next/server",
  "/app/apps/studio/.next/static",
]

const defaultPromptPrefix =
  "You are the Supabase Studio assistant. Follow the requested output format exactly. For SQL tasks, return executable PostgreSQL SQL first, then brief notes only if requested. Prefer safe migrations and avoid destructive operations unless explicitly requested."

const replacements = {
  STUDIO_OPENAI_BASE_URL:
    process.env.STUDIO_OPENAI_BASE_URL || process.env.OPENAI_BASE_URL || "",
  OPENAI_BASE_URL:
    process.env.OPENAI_BASE_URL || process.env.STUDIO_OPENAI_BASE_URL || "",
  OPENAI_API_KEY: process.env.OPENAI_API_KEY || "lm-studio",
  STUDIO_OPENAI_PROMPT_PREFIX:
    process.env.STUDIO_OPENAI_PROMPT_PREFIX || defaultPromptPrefix,
  STUDIO_OPENAI_MODELS: process.env.STUDIO_OPENAI_MODELS || "",
  STUDIO_OPENAI_MODEL:
    process.env.STUDIO_OPENAI_MODEL ||
    process.env.STUDIO_OPENAI_MODELS ||
    "",
  STUDIO_OPENAI_ADVANCED_MODEL:
    process.env.STUDIO_OPENAI_ADVANCED_MODEL ||
    process.env.STUDIO_OPENAI_MODEL ||
    process.env.STUDIO_OPENAI_MODELS ||
    "",
  STUDIO_OPENAI_EMBEDDING_MODEL:
    process.env.STUDIO_OPENAI_EMBEDDING_MODEL || "text-embedding-all-minilm-l6-v2-embedding",
}

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(full, files)
    } else if (entry.isFile() && full.endsWith(".js")) {
      files.push(full)
    }
  }
  return files
}

function encodedForSingleQuotedJs(value) {
  return JSON.stringify(String(value ?? "")).replace(/'/g, "\\u0027")
}

const bundleFiles = Array.from(
  new Set(
    bundleRoots
      .filter((root) => fs.existsSync(root))
      .flatMap((root) => walk(root))
  )
)

let touchedFiles = 0
let replacedTokens = 0

for (const file of bundleFiles) {
  let source = fs.readFileSync(file, "utf8")
  let changed = false

  for (const [envName, envValue] of Object.entries(replacements)) {
    const token = `__GS_ENV_${envName}__`
    if (!source.includes(token)) continue
    source = source.split(token).join(encodedForSingleQuotedJs(envValue))
    replacedTokens += 1
    changed = true
  }

  if (changed) {
    fs.writeFileSync(file, source)
    touchedFiles += 1
  }
}

console.log(
  `[lmstudio] runtime env token replacement complete: files=${touchedFiles}, tokens=${replacedTokens}`
)
