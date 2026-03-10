---
name: research
description: Grounds answers in best practices using MCP tools EXA, REF, and Perplexity. Use when the user asks for research, documentation review, best practices, source-backed comparisons, or error investigation before implementation.
---

# Research

## Purpose

Use this skill to build source-backed guidance before giving recommendations.

This skill always uses all three MCP tool families on each research task:
- EXA
- REF
- Perplexity

## When To Apply

Apply when requests include:
- research this topic
- best practices
- ground this before coding
- investigate this error
- compare approaches
- read docs first

## Required Workflow

Follow this order unless a hard blocker exists. If order changes, explain why.

1. Scope
- Capture topic, goal, stack, versions, and time sensitivity.
- Ask a focused clarification only if missing details would change conclusions.

2. EXA pass (broad discovery)
- Use `web_search_exa` for current landscape and source discovery.
- Use `get_code_context_exa` when implementation examples are needed.
- Collect 3-6 strong sources with publication or update recency when available.

3. REF pass (official docs)
- Use `ref_search_documentation` to find authoritative docs.
- Use `ref_read_url` on exact URLs returned by REF search.
- Prefer API references, migration guides, and release notes tied to the request.

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
  2) recent primary sources
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
- Validate fix direction against official docs plus at least one independent source.
- Recommend the simplest robust fix.

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
- All three tool families were used (EXA, REF, Perplexity).
- At least one official documentation source was read.
- Version-specific guidance is current and not deprecated.
- Recommendation is explicit and actionable.
