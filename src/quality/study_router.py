"""Route extraction records to the correct risk-of-bias tool."""

from __future__ import annotations

from src.models import ExtractionRecord, StudyDesign


class StudyRouter:
    def route_tool(self, record: ExtractionRecord) -> str:
        """Return the appropriate RoB tool name for a given study design.

        Routing rules (methodologically correct, aligned with MMAT 2018 and CASP):
          RCT                                        -> rob2
          NON_RANDOMIZED / COHORT / CASE_CONTROL     -> robins_i
          CROSS_SECTIONAL                            -> casp
            ROBINS-I (Risk Of Bias In Non-randomised Studies of Interventions)
            requires a defined intervention and comparator group. Cross-sectional
            designs are commonly survey-based or descriptive and lack the
            longitudinal intervention structure ROBINS-I expects. CASP
            (Critical Appraisal Skills Programme) cohort/cross-sectional
            checklist is more appropriate. If the specific study has a clear
            intervention component, the manuscript footnote should note this.
          MIXED_METHODS                              -> mmat (MMAT 2018, per Osman 2026)
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
        if design in {
            StudyDesign.NON_RANDOMIZED,
            StudyDesign.COHORT,
            StudyDesign.CASE_CONTROL,
        }:
            return "robins_i"
        if design in {StudyDesign.CROSS_SECTIONAL, StudyDesign.QUALITATIVE, StudyDesign.MIXED_METHODS}:
            # CROSS_SECTIONAL uses CASP (cohort/cross-sectional checklist);
            # QUALITATIVE and MIXED_METHODS also use CASP/MMAT as before.
            if design == StudyDesign.MIXED_METHODS:
                return "mmat"
            return "casp"
        # OTHER: systematic reviews, technical/narrative reports -- not amenable to ROBINS-I
        return "not_applicable"
