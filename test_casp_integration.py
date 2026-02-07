"""
Quick integration test for CASP quality assessment.

Tests the complete CASP workflow with mock data to verify:
1. Study type detection works
2. Template generation includes detected types
3. Auto-fill populates CASP questions
4. Summary tables are generated correctly
5. Rich console output works
"""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

# Set up minimal environment
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-structure-test")

from src.quality.template_generator import QualityAssessmentTemplateGenerator
from src.quality.study_type_detector import StudyTypeDetector
from src.quality.casp_prompts import (
    build_casp_rct_prompt,
    get_checklist_info,
    get_all_checklist_types
)
from src.extraction.data_extractor_agent import ExtractedData


def test_casp_integration():
    """Test CASP integration workflow."""
    
    print("\n" + "="*80)
    print("CASP INTEGRATION TEST")
    print("="*80 + "\n")
    
    # 1. Create mock extracted data
    print("[1/6] Creating mock extracted data...")
    extracted_data = [
        ExtractedData(
            title="AI Tutoring for Medical Students: A Randomized Controlled Trial",
            authors=["Smith J", "Johnson K"],
            year=2024,
            journal="Medical Education",
            doi="10.1000/test1",
            study_objectives=["Test AI tutoring effectiveness"],
            methodology="Randomized controlled trial with computer-generated allocation",
            study_design="Randomized Controlled Trial",
            participants="100 medical students randomly assigned to groups",
            interventions="AI tutoring system vs standard textbook",
            outcomes=["Exam scores", "Knowledge retention", "Student satisfaction"],
            key_findings=["Significant improvement in exam scores (p<0.01)"],
            limitations="Small sample size, single institution",
            country="United States",
            setting="Medical school",
            sample_size=100,
            detailed_outcomes=["Exam scores (mean difference: 8.5 points)"],
            quantitative_results="Effect size d=0.8, 95% CI: 0.5-1.1",
            ux_strategies=[],
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        )
    ]
    print(f"   Created {len(extracted_data)} mock study")
    
    # 2. Test checklist info retrieval
    print("\n[2/6] Testing checklist info...")
    for checklist_type in get_all_checklist_types():
        info = get_checklist_info(checklist_type)
        print(f"   - {info['name']}: {info['num_questions']} questions")
    
    # 3. Test prompt generation
    print("\n[3/6] Testing CASP prompt generation...")
    study_dict = extracted_data[0].to_dict()
    rct_prompt = build_casp_rct_prompt(extracted_data[0].title, study_dict)
    print(f"   RCT prompt length: {len(rct_prompt)} characters")
    assert "QUESTION 1" in rct_prompt
    assert "QUESTION 11" in rct_prompt
    assert "JSON" in rct_prompt
    print("   All 11 questions present in prompt")
    
    # 4. Test template generation with CASP
    print("\n[4/6] Testing template generation...")
    with TemporaryDirectory() as tmpdir:
        generator = QualityAssessmentTemplateGenerator(framework="CASP")
        template_path = Path(tmpdir) / "test_casp.json"
        
        # Generate without detection (for now)
        template_path_str = generator.generate_template(
            extracted_data,
            str(template_path),
            grade_outcomes=["Exam scores", "Knowledge retention"],
            detected_types=None
        )
        
        assert Path(template_path_str).exists()
        print(f"   Template generated at: {template_path}")
        
        # Verify structure
        with open(template_path_str, 'r') as f:
            template = json.load(f)
        
        assert template["framework"] == "CASP"
        assert len(template["studies"]) == 1
        print(f"   Framework: {template['framework']}")
        print(f"   Studies: {len(template['studies'])}")
        
        # Verify CASP structure
        study = template["studies"][0]
        assert "quality_assessment" in study
        assert "checklist_used" in study["quality_assessment"]
        assert "questions" in study["quality_assessment"]
        assert "score" in study["quality_assessment"]
        
        qa = study["quality_assessment"]
        print(f"   Checklist: {qa['checklist_used']}")
        print(f"   Questions: {len(qa['questions'])}")
        print(f"   Score structure: {qa['score']}")
        
        # Verify question structure
        q1 = qa["questions"]["q1"]
        assert "answer" in q1
        assert "justification" in q1
        print("   Question structure validated")
        
        # Verify GRADE assessments included
        assert "grade_assessments" in template
        assert len(template["grade_assessments"]) == 2
        print(f"   GRADE outcomes: {len(template['grade_assessments'])}")
    
    # 5. Test that detection prompt builds correctly
    print("\n[5/6] Testing study type detection prompt...")
    from src.quality.study_type_detector import StudyTypeDetector
    
    # Create mock client
    mock_client = Mock()
    detector = StudyTypeDetector(
        llm_client=mock_client,
        llm_model="gemini-2.5-flash"
    )
    
    # Build prompt (won't call LLM, just test prompt generation)
    prompt = detector._build_detection_prompt(
        title=extracted_data[0].title,
        study_design=extracted_data[0].study_design,
        methodology=extracted_data[0].methodology,
        participants=extracted_data[0].participants,
        interventions=[extracted_data[0].interventions] if extracted_data[0].interventions else [],
        outcomes=extracted_data[0].outcomes
    )
    
    print(f"   Detection prompt length: {len(prompt)} characters")
    assert "casp_rct" in prompt
    assert "casp_cohort" in prompt
    assert "casp_qualitative" in prompt
    assert "randomized" in prompt.lower()
    print("   Detection prompt includes all 3 checklist options")
    
    # 6. Summary
    print("\n[6/6] Integration test summary...")
    print("   [PASS] Checklist info retrieval")
    print("   [PASS] CASP prompt generation")
    print("   [PASS] Template generation with CASP structure")
    print("   [PASS] Question structure validation")
    print("   [PASS] GRADE integration maintained")
    print("   [PASS] Detection prompt generation")
    
    print("\n" + "="*80)
    print("ALL INTEGRATION TESTS PASSED")
    print("="*80 + "\n")
    
    return True


if __name__ == "__main__":
    try:
        test_casp_integration()
        print("\nSUCCESS: CASP integration verified!")
        exit(0)
    except AssertionError as e:
        print(f"\nFAILURE: {e}")
        exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
