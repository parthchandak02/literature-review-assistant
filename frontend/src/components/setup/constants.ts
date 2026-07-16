export const GEN_STEPS: { key: string; label: string; detail: string }[] = [
  { key: "start",            label: "Analyzing your research question", detail: "Understanding scope, domain, and intent" },
  { key: "web_research",     label: "Searching the web",                detail: "Discovering brand names, synonyms, and domain terminology" },
  { key: "web_research_fallback", label: "Web search unavailable",      detail: "Falling back to model knowledge for this generation" },
  { key: "web_research_done",label: "Processing search results",        detail: "Building research brief from web findings" },
  { key: "structuring",      label: "Generating PICO and criteria",     detail: "Keywords, inclusion/exclusion criteria, domain and scope" },
  { key: "topic_routing",    label: "Applying domain routing policy",   detail: "Selecting connector policy from confidence-scored topic signals" },
  { key: "finalizing",       label: "Finalizing your config",           detail: "Validating and serializing to YAML" },
]

export const WEB_RESEARCH_FALLBACK_STEP = "web_research_fallback"
export const WEB_RESEARCH_DONE_INDEX = GEN_STEPS.findIndex((s) => s.key === "web_research_done")
