---
name: research
description: Grounds answers in best practices using MCP tools EXA, REF, and Perplexity. Use when the user asks for research, documentation review, best practices, source-backed comparisons, or error investigation before implementation.
---

# Research

## Purpose

Use this skill to build source-backed guidance before giving recommendations.
Ground claims in current sources rather than memory, especially for
version-sensitive facts, APIs, and error messages.

This skill defaults to all three MCP tool families for substantial research tasks:
- EXA
- REF
- Perplexity

Official documentation is the primary authority. Use EXA for broad discovery
and Perplexity for cross-check synthesis, but prefer REF (and direct official
docs) when they cover the question.

## When To Apply

Apply when requests include:
- research this topic
- best practices
- ground this before coding
- investigate this error
- compare approaches
- read docs first

## Tooling (soft-gate)

Use whatever research tools are available in the current environment:

- Prefer the EXA / REF / Perplexity MCP tools below when present.
- If a family or tool is unavailable, fall back to the next-best available
  method (other search/fetch tools, or reading official docs directly).
- Never fail or refuse the skill because a specific tool is missing; document
  the fallback and say which sources were actually used.
- Always discover/read tool schema before invocation.

## Required Workflow

Follow this order unless a hard blocker exists. If order changes, explain why.

1. Build a context packet before searching
- Capture, and mark "unknown" if genuinely unknown:
  - topic and desired outcome
  - stack, exact versions of relevant dependencies
  - environment (OS, runtime, deployment target)
  - constraints (performance, security, compatibility, simplicity)
  - exact error text / stack trace / repro steps, if debugging
  - what has already been tried
  - recency requirement (for example "as of `<current year>`")
  - desired output shape (decision, comparison, migration path, code pattern, checklist)
- Ask a focused clarification only if a missing field would change conclusions.

2. EXA pass (broad discovery)
- Discover the available Exa MCP tool schemas first, then use the repo's current Exa search and code-context tools for discovery.
- Collect 3-6 strong sources with publication or update recency when available.

3. REF pass (official docs first)
- Discover the available Ref MCP tool schemas first, then use the repo's current Ref documentation-search and URL-read tools.
- Prefer API references, migration guides, and release notes tied to the request.
- Prefer the exact version in use over the latest if they differ.
- Treat official docs as the authoritative baseline for API shape, deprecations, and supported behavior.

4. Perplexity pass (cross-check and synthesis)
- Use `perplexity_search` to gather additional candidate sources.
- Use one synthesis tool:
  - `perplexity_ask` for quick factual guidance
  - `perplexity_reason` for complex comparisons and tradeoffs
  - `perplexity_research` for deep multi-source investigations
- Cross-check key claims from EXA and REF before final recommendations.

5. Resolve conflicts
- If sources disagree, prioritize:
  1) official docs and release notes
  2) recent primary sources (maintainers, changelogs)
  3) secondary summaries
- State conflicts explicitly and choose one recommendation.

## Output Format

Use this structure by default:

1. Recommendation
- One clear approach.

2. Why this approach
- 2-4 concise reasons focused on robustness and simplicity.

3. Implementation notes
- Practical steps, version caveats, and constraints.

4. Risks and checks
- Failure modes and how to validate quickly.

5. Sources
- Include links for non-obvious, version-sensitive, or disputed claims.

## Error Investigation Mode

When debugging or fixing errors:
- Identify likely root cause before suggesting changes.
- Avoid temporary patches that hide underlying issues.
- Include the full error context (message, stack trace excerpt, repro steps, expected vs observed) in queries.
- Validate fix direction against official docs plus at least one independent source.
- Recommend the simplest robust fix that addresses the root cause.

## Parallel Mode (Optional)

Use parallel agents only for broad or high-ambiguity research where one pass is too slow.

Strict guardrails:
- Launch at most 3 agents in parallel.
- Assign non-overlapping scopes per agent (for example: official docs, community examples, and recent changes).
- Merge results through one final synthesis pass that resolves conflicts using the standard source priority rules.

## Query Templates

EXA discovery:
- "<topic> <framework> <version> best practices <year>"

EXA code context:
- "<framework> <api or feature> examples <version>"

REF documentation:
- "<framework or library> <api or feature> official documentation"

Perplexity cross-check:
- "Given these approaches for <topic>, which is best for <version> and why?"

## Quality Gate

Before finalizing research output, verify:
- EXA, REF, and Perplexity were used when available; any fallback was documented.
- At least one official documentation source was read.
- Version-specific guidance is current and not deprecated.
- Recommendation is explicit and actionable.
- Material conflicts between sources were surfaced and resolved, not silently dropped.
