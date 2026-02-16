"""Route extraction records to the correct risk-of-bias tool."""

from __future__ import annotations

from src.models import ExtractionRecord, StudyDesign


class StudyRouter:
    def route_tool(self, record: ExtractionRecord) -> str:
        design = record.study_design
        if design == StudyDesign.RCT:
            return "rob2"
        if design in {StudyDesign.NON_RANDOMIZED, StudyDesign.COHORT, StudyDesign.CASE_CONTROL}:
            return "robins_i"
        if design == StudyDesign.QUALITATIVE:
            return "casp"
        return "robins_i"
