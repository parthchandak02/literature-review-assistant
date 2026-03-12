---
name: protocol-generator
description: Generates PROSPERO-format protocol from ReviewConfig. Use when building src/protocol/ or Phase 2 protocol output.
---

# Protocol Generator Implementation

Guide for implementing PROSPERO-format protocol generation (Phase 2).

## Output

`ProtocolDocument` is the structured protocol model used by the pipeline. Primary run artifact is `doc_protocol.md`; full PROSPERO-oriented artifacts are also emitted as `doc_prospero_registration.md` and `doc_prospero_registration.docx` when available.

## Required Fields

- research_question, pico (PICOConfig)
- eligibility_criteria (List[str])
- planned_databases (List[str])
- planned_screening_method (e.g. "Dual AI reviewer with adjudication")
- planned_rob_tools (e.g. ["rob2", "robins_i", "casp"])
- planned_synthesis_method
- prospero_id (optional)

## Implementation

`src/protocol/generator.py` -- takes `ReviewConfig`, produces `ProtocolDocument`.

LLM-drafted for narrative sections where structured data is insufficient.

## Integration

Runs as part of Phase 2 (Search). Protocol generated after search strategy is defined, before screening begins.
