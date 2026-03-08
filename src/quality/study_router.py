"""Route extraction records to the correct risk-of-bias tool."""

from __future__ import annotations

from src.models import ExtractionRecord, StudyDesign


class StudyRouter:
    def route_tool(self, record: ExtractionRecord) -> str:
        """Return the appropriate RoB tool name for a given study design.

        Routing rules (methodologically correct, aligned with MMAT 2018 and CASP):

          RCT                                              -> rob2
          NON_RANDOMIZED / QUASI_EXPERIMENTAL              -> robins_i
            QUASI_EXPERIMENTAL: non-equivalent control group or interrupted time
            series. Has a comparator but no random allocation. ROBINS-I applies
            because there is still a defined intervention and comparison.
          COHORT / CASE_CONTROL                            -> robins_i
          PRE_POST                                         -> mmat
            Single-group before/after study with no control arm. Corresponds to
            MMAT 2018 category 4 (quantitative descriptive). The CASP cohort
            checklist is not appropriate here because there is no comparator;
            MMAT quantitative descriptive criteria are the correct appraisal.
          CROSS_SECTIONAL / QUALITATIVE / USABILITY_STUDY -> casp
            ROBINS-I requires a defined intervention and comparator; cross-
            sectional and usability-only designs lack both. CASP checklist
            (cohort/cross-sectional variant) is more appropriate.
          MIXED_METHODS                                    -> mmat (MMAT 2018)
          DEVELOPMENT_STUDY                                -> not_applicable
            System design/architecture papers. Primary contribution is the tool
            itself, not an outcomes study. No standard RoB appraisal applies;
            disclosed separately in the study characteristics table.
          PROTOCOL / CONFERENCE_ABSTRACT / NARRATIVE_REVIEW / OTHER -> not_applicable
            Not primary interventional studies. Disclosed separately in the RoB
            figure caption and Methods transparency note.
        """
        design = record.study_design
        if design == StudyDesign.RCT:
            return "rob2"
        if design in {
            StudyDesign.NON_RANDOMIZED,
            StudyDesign.QUASI_EXPERIMENTAL,
            StudyDesign.COHORT,
            StudyDesign.CASE_CONTROL,
        }:
            return "robins_i"
        if design == StudyDesign.MIXED_METHODS:
            return "mmat"
        if design == StudyDesign.PRE_POST:
            # MMAT 2018 category 4: quantitative descriptive (single group, no comparator)
            return "mmat"
        if design in {
            StudyDesign.CROSS_SECTIONAL,
            StudyDesign.QUALITATIVE,
            StudyDesign.USABILITY_STUDY,
        }:
            return "casp"
        # DEVELOPMENT_STUDY, PROTOCOL, CONFERENCE_ABSTRACT, NARRATIVE_REVIEW, OTHER:
        # not primary interventional studies -- not amenable to ROBINS-I or RoB 2.
        # Disclosed separately in the RoB figure caption and Methods transparency note.
        return "not_applicable"
