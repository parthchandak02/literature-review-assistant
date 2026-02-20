"""Route extraction records to the correct risk-of-bias tool."""

from __future__ import annotations

from src.models import ExtractionRecord, StudyDesign


class StudyRouter:
    def route_tool(self, record: ExtractionRecord) -> str:
        """Return the appropriate RoB tool name for a given study design.

        Routing rules (methodologically correct):
          RCT                                        -> rob2
          NON_RANDOMIZED / COHORT / CASE_CONTROL     -> robins_i
          CROSS_SECTIONAL / MIXED_METHODS            -> robins_i (may have intervention component)
          QUALITATIVE                                -> casp
          OTHER                                      -> not_applicable
            OTHER covers: systematic reviews, literature reviews, technical
            reports, proof-of-concept papers, narrative overviews.  None of
            these are primary interventional studies, so ROBINS-I does not
            apply.  They are disclosed separately in the RoB figure caption.
        """
        design = record.study_design
        if design == StudyDesign.RCT:
            return "rob2"
        if design in {StudyDesign.NON_RANDOMIZED, StudyDesign.COHORT, StudyDesign.CASE_CONTROL,
                      StudyDesign.CROSS_SECTIONAL, StudyDesign.MIXED_METHODS}:
            return "robins_i"
        if design == StudyDesign.QUALITATIVE:
            return "casp"
        # OTHER: systematic reviews, technical/narrative reports -- not amenable to ROBINS-I
        return "not_applicable"
