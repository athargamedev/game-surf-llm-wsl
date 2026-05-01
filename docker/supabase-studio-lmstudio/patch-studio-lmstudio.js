const fs = require('fs')
const path = require('path')

const serverDir = '/app/apps/studio/.next/server'

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(full, files)
    } else if (entry.isFile() && full.endsWith('.js')) {
      files.push(full)
    }
  }
  return files
}

function localModelExpr(modelVar) {
  return `(process.env.STUDIO_OPENAI_ADVANCED_MODEL&&${modelVar}==="gpt-5.3-codex"?process.env.STUDIO_OPENAI_ADVANCED_MODEL:process.env.STUDIO_OPENAI_MODEL||${modelVar})`
}

let patchedFiles = 0
let providerPatches = 0
let fetchPatches = 0
let bodyModelPatches = 0
let providerOptionsPatches = 0

for (const file of walk(serverDir)) {
  let source = fs.readFileSync(file, 'utf8')
  const before = source

  source = source.replace(
    /model:\(0,([A-Za-z_$][\w$]*)\.openai\)\(([A-Za-z_$][\w$]*)\),providerOptions/g,
    (_match, providerVar, modelVar) => {
      providerPatches += 1
      const model = localModelExpr(modelVar)
      return `model:(process.env.STUDIO_OPENAI_BASE_URL||process.env.OPENAI_BASE_URL?(0,${providerVar}.createOpenAI)({apiKey:process.env.OPENAI_API_KEY||"lm-studio",baseURL:process.env.STUDIO_OPENAI_BASE_URL||process.env.OPENAI_BASE_URL})(${model}):(0,${providerVar}.openai)(${model})),providerOptions`
    }
  )

  source = source.replace(/providerOptions:\{openai:([A-Za-z_$][\w$]*)\}/g, (_match, optionsVar) => {
    providerOptionsPatches += 1
    return `providerOptions:{openai:process.env.STUDIO_OPENAI_BASE_URL||process.env.OPENAI_BASE_URL?{}:${optionsVar}}`
  })

  source = source.replace(
    /fetch\("https:\/\/api\.openai\.com\/v1\/chat\/completions"/g,
    () => {
      fetchPatches += 1
      return 'fetch((process.env.STUDIO_OPENAI_BASE_URL||process.env.OPENAI_BASE_URL||"https://api.openai.com/v1")+"/chat/completions"'
    }
  )

  source = source.replace(
    /body:JSON\.stringify\(\{model:([A-Za-z_$][\w$]*),messages:/g,
    (_match, modelVar) => {
      bodyModelPatches += 1
      return `body:JSON.stringify({model:${localModelExpr(modelVar)},messages:`
    }
  )

  if (source !== before) {
    fs.writeFileSync(file, source)
    patchedFiles += 1
  }
}

if (providerPatches === 0 && fetchPatches === 0) {
  throw new Error('No Supabase Studio AI call sites were patched')
}

console.log(
  `Patched ${patchedFiles} files: ${providerPatches} provider calls, ${fetchPatches} fetch URLs, ${bodyModelPatches} request body models, ${providerOptionsPatches} provider option blocks.`
)
