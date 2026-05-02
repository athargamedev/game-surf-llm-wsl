const fs = require('fs')
const path = require('path')

const bundleRoots = [
  '/app/apps/studio/.next/server',
  '/app/apps/studio/.next/static',
]

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

function envValueExpr(envName) {
  return `(JSON.parse('__GS_ENV_${envName}__'))`
}

function firstModelFromEnvExpr(envName) {
  return `(${envValueExpr(envName)}).split(",").map((id)=>id.trim()).find(Boolean)`
}

function localModelExpr(modelVar) {
  const baseModel = firstModelFromEnvExpr("STUDIO_OPENAI_MODEL")
  const advancedModel = firstModelFromEnvExpr("STUDIO_OPENAI_ADVANCED_MODEL")
  return `(${advancedModel}&&${modelVar}==="gpt-5.3-codex"?${advancedModel}:${baseModel}||${modelVar})`
}

function localModelCatalogExpr() {
  return `Array.from(new Set([...((${envValueExpr("STUDIO_OPENAI_MODELS")}).split(",")),...((${envValueExpr("STUDIO_OPENAI_MODEL")}).split(",")),...((${envValueExpr("STUDIO_OPENAI_ADVANCED_MODEL")}).split(","))].map((id)=>id.trim()).filter(Boolean)))`
}

let patchedFiles = 0
let providerPatches = 0
let fetchPatches = 0
let bodyModelPatches = 0
let providerOptionsPatches = 0
let staticModelCatalogPatches = 0
let legacyModelModulePatches = 0
let orgSettingsClientPatches = 0
let orgSettingsServerPatches = 0
let embeddingPatches = 0

const bundleFiles = Array.from(
  new Set(
    bundleRoots
      .filter((root) => fs.existsSync(root))
      .flatMap((root) => walk(root))
  )
)

for (const file of bundleFiles) {
  let source = fs.readFileSync(file, 'utf8')
  const before = source
  const studioOpenAIBaseUrl = envValueExpr("STUDIO_OPENAI_BASE_URL")
  const openAIBaseUrl = envValueExpr("OPENAI_BASE_URL")
  const openAIApiKey = envValueExpr("OPENAI_API_KEY")
  const promptPrefix = envValueExpr("STUDIO_OPENAI_PROMPT_PREFIX")

  source = source.replace(
    /model:\(0,([A-Za-z_$][\w$]*)\.openai\)\(([A-Za-z_$][\w$]*)\),providerOptions/g,
    (_match, providerVar, modelVar) => {
      providerPatches += 1
      const model = localModelExpr(modelVar)
      return `model:(${studioOpenAIBaseUrl}||${openAIBaseUrl}?(0,${providerVar}.createOpenAI)({apiKey:${openAIApiKey}||"lm-studio",baseURL:${studioOpenAIBaseUrl}||${openAIBaseUrl}})(${model}):(0,${providerVar}.openai)(${model})),providerOptions`
    }
  )

  source = source.replace(/providerOptions:\{openai:([A-Za-z_$][\w$]*)\}/g, (_match, optionsVar) => {
    providerOptionsPatches += 1
    return `providerOptions:{openai:${studioOpenAIBaseUrl}||${openAIBaseUrl}?{}:${optionsVar}}`
  })

  source = source.replace(
    /fetch\("https:\/\/api\.openai\.com\/v1\/chat\/completions"/g,
    () => {
      fetchPatches += 1
      return `fetch((${studioOpenAIBaseUrl}||${openAIBaseUrl}||"https://api.openai.com/v1")+"/chat/completions"`
    }
  )

  source = source.replace(
    /fetch\("https:\/\/api\.openai\.com\/v1\/embeddings"/g,
    () => {
      embeddingPatches += 1
      return `fetch((${studioOpenAIBaseUrl}||${openAIBaseUrl}||"https://api.openai.com/v1")+"/embeddings"`
    }
  )

  // Fix: Ensure embedding 'input' is always handled correctly for local models
  source = source.replace(
    /body:JSON\.stringify\(\{model:("text-embedding-3-small"|([A-Za-z_$][\w$]*)),input:([A-Za-z_$][\w$]*)\}\)/g,
    (_match, modelVar, _dummy, inputVar) => {
      return `body:JSON.stringify({model:${envValueExpr("STUDIO_OPENAI_EMBEDDING_MODEL")},input:typeof ${inputVar} === 'object' && ${inputVar}.prompt ? ${inputVar}.prompt : ${inputVar}})`
    }
  )

  source = source.replace(
    /body:JSON\.stringify\(\{model:([A-Za-z_$][\w$]*),messages:([A-Za-z_$][\w$]*),/g,
    (_match, modelVar, messagesVar) => {
      bodyModelPatches += 1
      return `body:JSON.stringify({
        model:${localModelExpr(modelVar)},
        temperature: 0,
        top_p: 0.1,
        max_tokens: 4096,
        messages:((${studioOpenAIBaseUrl}||${openAIBaseUrl})&&Array.isArray(${messagesVar})?[{role:"system",content:${promptPrefix}||"You are an expert PostgreSQL assistant for Supabase Studio. IMPORTANT: Always return executable SQL code blocks first. Do not provide long explanations unless asked. For migrations, use safe 'CREATE IF NOT EXISTS' patterns. If tools are provided, follow the tool-calling format strictly."},...${messagesVar}]:${messagesVar}),`
    }
  )

  source = source.replace(
    /let\{data:([A-Za-z_$][\w$]*),error:([A-Za-z_$][\w$]*)\}=await \(0,([A-Za-z_$][\w$]*)\.patch\)\("\/platform\/organizations\/\{slug\}",\{params:\{path:\{slug:([A-Za-z_$][\w$]*)\}\},body:([A-Za-z_$][\w$]*)\}\);/g,
    (_match, dataVar, errorVar, clientVar, _slugVar, bodyVar) => {
      orgSettingsClientPatches += 1
      return `let{data:${dataVar},error:${errorVar}}=await (0,${clientVar}.patch)("/platform/organizations",{body:${bodyVar}});`
    }
  )

  source = source.replace(
    /body:JSON\.stringify\(\{model:"text-embedding-3-small",input:([A-Za-z_$][\w$]*)\}\)/g,
    (_match, inputVar) => {
      return `body:JSON.stringify({model:${envValueExpr("STUDIO_OPENAI_EMBEDDING_MODEL")},input:${inputVar}})`
    }
  )

  source = source.replace(
    'async function s(e,t){let{method:r}=e;if("GET"===r)return n(e,t);t.setHeader("Allow",["GET"]),t.status(405).json({data:null,error:{message:`Method ${r} Not Allowed`}})}[a]=o.then?(await o)():o;let n=async(e,t)=>{let r=[{id:1,name:process.env.DEFAULT_ORGANIZATION_NAME||"Default Organization",slug:"default-org-slug",billing_email:"billing@supabase.co",plan:{id:"enterprise",name:"Enterprise"}}];return t.status(200).json(r)};',
    'async function s(e,t){let{method:r}=e;if("GET"===r)return n(e,t);if("PATCH"===r)return l(e,t);t.setHeader("Allow",["GET","PATCH"]),t.status(405).json({data:null,error:{message:`Method ${r} Not Allowed`}})}[a]=o.then?(await o)():o;let l=async(e,t)=>{let r=e.body||{},a={id:1,name:r.name||process.env.DEFAULT_ORGANIZATION_NAME||"Default Organization",slug:r.slug||"default-org-slug",billing_email:r.billing_email||"billing@supabase.co",plan:{id:"enterprise",name:"Enterprise"},opt_in_tags:Array.isArray(r.opt_in_tags)?r.opt_in_tags:[]};return t.status(200).json(a)},n=async(e,t)=>{let r=[{id:1,name:process.env.DEFAULT_ORGANIZATION_NAME||"Default Organization",slug:"default-org-slug",billing_email:"billing@supabase.co",plan:{id:"enterprise",name:"Enterprise"}}];return t.status(200).json(r)};'
  )
  if (source !== before && source.includes('if("PATCH"===r)return l(e,t);')) {
    orgSettingsServerPatches += 1
  }

  source = source.replace(
    /b\(\{id:"gpt-5\.4-nano",reasoningEffort:"none"\}\);let c=\[b\(\{id:"gpt-5\.4-nano",requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"\}\),b\(\{id:"gpt-5\.3-codex",requiresAdvanceModelEntitlement:!0,reasoningEffort:"low"\}\)\],d=Object\.fromEntries\(c\.map\(a=>\[a\.id,a\]\)\),e="gpt-5\.4-nano";a\.s\(\["ASSISTANT_MODELS",0,c,"DEFAULT_ASSISTANT_BASE_MODEL_ID",0,e,"defaultAssistantModelId",0,function\(a\)\{return a\?"gpt-5\.3-codex":e\},"isAdvanceOnlyModelId",0,function\(a\)\{return a in d&&d\[a\]\.requiresAdvanceModelEntitlement\},"isAssistantBaseModelId",0,function\(a\)\{return a in d&&!d\[a\]\.requiresAdvanceModelEntitlement\},"isKnownAssistantModelId",0,function\(a\)\{return Object\.hasOwn\(d,a\)\}\]\)/g,
    () => {
      staticModelCatalogPatches += 1
      const modelCatalogExpr = localModelCatalogExpr()
      const baseFromEnvExpr = firstModelFromEnvExpr("STUDIO_OPENAI_MODEL")
      const advancedFromEnvExpr = firstModelFromEnvExpr("STUDIO_OPENAI_ADVANCED_MODEL")
      return `;(()=>{const __gsModelCatalog=${modelCatalogExpr},__gsBase=${baseFromEnvExpr}||__gsModelCatalog[0]||"gpt-5.4-nano",__gsAdvanced=${advancedFromEnvExpr}||__gsModelCatalog.find(a=>a!==__gsBase)||__gsBase,c=[b({id:__gsBase,requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"}),...(__gsAdvanced&&__gsAdvanced!==__gsBase?[b({id:__gsAdvanced,requiresAdvanceModelEntitlement:!0,reasoningEffort:"low"})]:[]),...__gsModelCatalog.filter(a=>a!==__gsBase&&a!==__gsAdvanced).map(a=>b({id:a,requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"}))],d=Object.fromEntries(c.map(a=>[a.id,a])),e=__gsBase;a.s(["ASSISTANT_MODELS",0,c,"DEFAULT_ASSISTANT_BASE_MODEL_ID",0,e,"defaultAssistantModelId",0,function(a){return a?__gsAdvanced:e},"isAdvanceOnlyModelId",0,function(a){return a in d&&d[a].requiresAdvanceModelEntitlement},"isAssistantBaseModelId",0,function(a){return a in d&&!d[a].requiresAdvanceModelEntitlement},"isKnownAssistantModelId",0,function(a){return Object.hasOwn(d,a)}])})()`
    }
  )

  source = source.replace(
    /function ([A-Za-z_$][\w$]*)\(e\)\{return\{requiresAdvanceModelEntitlement:!1,\.\.\.e\}\}let ([A-Za-z_$][\w$]*)=\1\(\{id:"gpt-5\.4-nano",reasoningEffort:"none"\}\),([A-Za-z_$][\w$]*)=Object\.fromEntries\(\[\1\(\{id:"gpt-5\.4-nano",requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"\}\),\1\(\{id:"gpt-5\.3-codex",requiresAdvanceModelEntitlement:!0,reasoningEffort:"low"\}\)\]\.map\(e=>\[e\.id,e\]\)\),([A-Za-z_$][\w$]*)=\{bedrock:\{models:\{"anthropic\.claude-3-7-sonnet-20250219-v1:0":\{promptProviderOptions:\{bedrock:\{cachePoint:\{type:"default"\}\}\},default:!1\},"openai\.gpt-oss-120b-1:0":\{default:!0\}\}\},openai:\{models:\{"gpt-5\.3-codex":\{default:!1\},"gpt-5\.4-nano":\{default:!0\}\},providerOptions:\{openai:\{store:!1\}\}\}\};e\.s\(\["DEFAULT_ASSISTANT_ADVANCE_MODEL_ID",0,"gpt-5\.3-codex","DEFAULT_ASSISTANT_BASE_MODEL_ID",0,"gpt-5\.4-nano","DEFAULT_COMPLETION_MODEL",0,\2,"PROVIDERS",0,\4,"getAssistantModelEntry",0,function\(e\)\{return \3\[e\]\},"getDefaultModelForProvider",0,function\(e\)\{let [A-Za-z_$][\w$]*=\4\[e\]\?\.models;if\([A-Za-z_$][\w$]*\)return Object\.keys\([A-Za-z_$][\w$]*\)\.find\(e=>[A-Za-z_$][\w$]*\[e\]\?\.default\)\},"isAssistantBaseModelId",0,function\(e\)\{return e in \3&&!\3\[e\]\.requiresAdvanceModelEntitlement\},"isKnownAssistantModelId",0,function\(e\)\{return Object\.hasOwn\(\3,e\)\}\]\)/g,
    (_match, builderVar, defaultModelVar, modelIndexVar, providersVar) => {
      legacyModelModulePatches += 1
      const modelCatalogExpr = localModelCatalogExpr()
      const baseFromEnvExpr = firstModelFromEnvExpr("STUDIO_OPENAI_MODEL")
      const advancedFromEnvExpr = firstModelFromEnvExpr("STUDIO_OPENAI_ADVANCED_MODEL")
      return `function ${builderVar}(e){return{requiresAdvanceModelEntitlement:!1,...e}};(()=>{const __gsModelCatalog=${modelCatalogExpr},__gsBase=${baseFromEnvExpr}||__gsModelCatalog[0]||"gpt-5.4-nano",__gsAdvanced=${advancedFromEnvExpr}||__gsModelCatalog.find(e=>e!==__gsBase)||__gsBase,${defaultModelVar}=${builderVar}({id:__gsBase,reasoningEffort:"none"}),${modelIndexVar}=Object.fromEntries([${builderVar}({id:__gsBase,requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"}),...__gsAdvanced&&__gsAdvanced!==__gsBase?[${builderVar}({id:__gsAdvanced,requiresAdvanceModelEntitlement:!0,reasoningEffort:"low"})]:[],...__gsModelCatalog.filter(e=>e!==__gsBase&&e!==__gsAdvanced).map(e=>${builderVar}({id:e,requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"}))].map(e=>[e.id,e])),${providersVar}={bedrock:{models:{"anthropic.claude-3-7-sonnet-20250219-v1:0":{promptProviderOptions:{bedrock:{cachePoint:{type:"default"}}},default:!1},"openai.gpt-oss-120b-1:0":{default:!0}}},openai:{models:Object.fromEntries([__gsBase,...__gsModelCatalog.filter(e=>e!==__gsBase&&e!==__gsAdvanced),...__gsAdvanced&&__gsAdvanced!==__gsBase?[__gsAdvanced]:[]].map((e,t)=>[e,{default:0===t}])),providerOptions:{openai:{store:!1}}}};e.s(["DEFAULT_ASSISTANT_ADVANCE_MODEL_ID",0,__gsAdvanced,"DEFAULT_ASSISTANT_BASE_MODEL_ID",0,__gsBase,"DEFAULT_COMPLETION_MODEL",0,${defaultModelVar},"PROVIDERS",0,${providersVar},"getAssistantModelEntry",0,function(e){return ${modelIndexVar}[e]},"getDefaultModelForProvider",0,function(e){let t=${providersVar}[e]?.models;if(t)return Object.keys(t).find(e=>t[e]?.default)},"isAssistantBaseModelId",0,function(e){return e in ${modelIndexVar}&&!${modelIndexVar}[e].requiresAdvanceModelEntitlement},"isKnownAssistantModelId",0,function(e){return Object.hasOwn(${modelIndexVar},e)}])})()`
    }
  )

  source = source.replace(
    /function ([A-Za-z_$][\w$]*)\(e\)\{return\{requiresAdvanceModelEntitlement:!1,\.\.\.e\}\}\1\(\{id:"gpt-5\.4-nano",reasoningEffort:"none"\}\);let ([A-Za-z_$][\w$]*)=\[\1\(\{id:"gpt-5\.4-nano",requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"\}\),\1\(\{id:"gpt-5\.3-codex",requiresAdvanceModelEntitlement:!0,reasoningEffort:"low"\}\)\],([A-Za-z_$][\w$]*)=Object\.fromEntries\(\2.map\(e=>\[e\.id,e\]\)\),([A-Za-z_$][\w$]*)="gpt-5\.4-nano";function ([A-Za-z_$][\w$]*)\(e\)\{return Object\.hasOwn\(\3,e\)\}e\.s\(\["ASSISTANT_MODELS",0,\2,"DEFAULT_ASSISTANT_BASE_MODEL_ID",0,\4,"defaultAssistantModelId",0,function\(e\)\{return e\?"gpt-5\.3-codex":\4\},"isAdvanceOnlyModelId",0,function\(e\)\{return e in \3&&\3\[e\]\.requiresAdvanceModelEntitlement\},"isAssistantBaseModelId",0,function\(e\)\{return e in \3&&!\3\[e\]\.requiresAdvanceModelEntitlement\},"isKnownAssistantModelId",0,\5\](?:,([0-9]+))?\)/g,
    (_match, builderVar, modelArrayVar, modelIndexVar, defaultBaseVar, knownFnVar, moduleId) => {
      staticModelCatalogPatches += 1
      const modelCatalogExpr = localModelCatalogExpr()
      const baseFromEnvExpr = firstModelFromEnvExpr("STUDIO_OPENAI_MODEL")
      const advancedFromEnvExpr = firstModelFromEnvExpr("STUDIO_OPENAI_ADVANCED_MODEL")
      const moduleIdSuffix = moduleId ? `,${moduleId}` : ''
      return `function ${builderVar}(e){return{requiresAdvanceModelEntitlement:!1,...e}};(()=>{const __gsModelCatalog=${modelCatalogExpr},__gsBase=${baseFromEnvExpr}||__gsModelCatalog[0]||"gpt-5.4-nano",__gsAdvanced=${advancedFromEnvExpr}||__gsModelCatalog.find(e=>e!==__gsBase)||__gsBase,${modelArrayVar}=[${builderVar}({id:__gsBase,requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"}),...__gsAdvanced&&__gsAdvanced!==__gsBase?[${builderVar}({id:__gsAdvanced,requiresAdvanceModelEntitlement:!0,reasoningEffort:"low"})]:[],...__gsModelCatalog.filter(e=>e!==__gsBase&&e!==__gsAdvanced).map(e=>${builderVar}({id:e,requiresAdvanceModelEntitlement:!1,reasoningEffort:"low"}))],${modelIndexVar}=Object.fromEntries(${modelArrayVar}.map(e=>[e.id,e])),${defaultBaseVar}=__gsBase;function ${knownFnVar}(e){return Object.hasOwn(${modelIndexVar},e)}e.s(["ASSISTANT_MODELS",0,${modelArrayVar},"DEFAULT_ASSISTANT_BASE_MODEL_ID",0,${defaultBaseVar},"defaultAssistantModelId",0,function(e){return e?__gsAdvanced:${defaultBaseVar}},"isAdvanceOnlyModelId",0,function(e){return e in ${modelIndexVar}&&${modelIndexVar}[e].requiresAdvanceModelEntitlement},"isAssistantBaseModelId",0,function(e){return e in ${modelIndexVar}&&!${modelIndexVar}[e].requiresAdvanceModelEntitlement},"isKnownAssistantModelId",0,${knownFnVar}]${moduleIdSuffix})})()`
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
  `Patched ${patchedFiles} files: ${providerPatches} provider calls, ${fetchPatches} fetch URLs, ${embeddingPatches} embedding URLs, ${bodyModelPatches} request body models, ${providerOptionsPatches} provider option blocks, ${staticModelCatalogPatches} static model catalogs, ${legacyModelModulePatches} legacy model modules, ${orgSettingsClientPatches} org settings client calls, ${orgSettingsServerPatches} org settings server routes.`
)
