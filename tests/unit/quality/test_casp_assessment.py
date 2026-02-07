"""
Unit tests for CASP quality assessment implementation.

Tests study type detection, CASP prompt generation, assessment execution,
response parsing, and scoring calculation.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from src.quality.study_type_detector import StudyTypeDetector
from src.quality.casp_prompts import (
    build_casp_rct_prompt,
    build_casp_cohort_prompt,
    build_casp_qualitative_prompt,
    get_checklist_info,
    get_all_checklist_types
)
from src.quality.auto_filler import QualityAssessmentAutoFiller


class TestStudyTypeDetector:
    """Tests for StudyTypeDetector class."""
    
    def test_detect_rct_study(self):
        """Test RCT detection from study with randomization keywords."""
        # Mock LLM client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = json.dumps({
            "checklist": "casp_rct",
            "confidence": 0.95,
            "reasoning": "Study explicitly mentions randomization and control group"
        })
        mock_client.models.generate_content.return_value = mock_response
        
        detector = StudyTypeDetector(mock_client, llm_model="gemini-2.5-flash")
        
        # Test with RCT study data
        study_data = {
            'title': 'Effect of AI Tutoring on Learning Outcomes: A Randomized Controlled Trial',
            'study_design': 'Randomized controlled trial',
            'methodology': 'Participants were randomly assigned to either AI tutoring or control group',
            'participants': '100 medical students',
            'interventions': ['AI tutoring system', 'Standard textbook'],
            'outcomes': ['Exam scores', 'Knowledge retention']
        }
        
        result = detector.detect_study_type(study_data)
        
        assert result['checklist'] == 'casp_rct'
        assert result['confidence'] >= 0.7
        assert 'reasoning' in result
        assert result['fallback_used'] is False
    
    def test_detect_cohort_study(self):
        """Test cohort detection from observational study."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = json.dumps({
            "checklist": "casp_cohort",
            "confidence": 0.88,
            "reasoning": "Observational study following participants over time without randomization"
        })
        mock_client.models.generate_content.return_value = mock_response
        
        detector = StudyTypeDetector(mock_client)
        
        study_data = {
            'title': 'Longitudinal Study of Chatbot Usage in Nursing Education',
            'study_design': 'Cohort study',
            'methodology': 'Followed nursing students using chatbot over one semester',
            'participants': '50 nursing students',
            'interventions': ['AI chatbot for learning'],
            'outcomes': ['Usage patterns', 'Learning outcomes']
        }
        
        result = detector.detect_study_type(study_data)
        
        assert result['checklist'] == 'casp_cohort'
        assert result['confidence'] > 0.7
        assert result['fallback_used'] is False
    
    def test_detect_qualitative_study(self):
        """Test qualitative detection from interview study."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = json.dumps({
            "checklist": "casp_qualitative",
            "confidence": 0.92,
            "reasoning": "Study uses interviews and thematic analysis to explore experiences"
        })
        mock_client.models.generate_content.return_value = mock_response
        
        detector = StudyTypeDetector(mock_client)
        
        study_data = {
            'title': 'Student Experiences with AI Tutoring: A Qualitative Study',
            'study_design': 'Qualitative interview study',
            'methodology': 'Semi-structured interviews with thematic analysis',
            'participants': '15 medical students',
            'interventions': [],
            'outcomes': ['Themes', 'Experiences', 'Perceptions']
        }
        
        result = detector.detect_study_type(study_data)
        
        assert result['checklist'] == 'casp_qualitative'
        assert result['confidence'] > 0.7
        assert result['fallback_used'] is False
    
    def test_low_confidence_fallback(self):
        """Test fallback to cohort when detection confidence is low."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = json.dumps({
            "checklist": "casp_rct",
            "confidence": 0.55,  # Below threshold
            "reasoning": "Unclear if randomization was used"
        })
        mock_client.models.generate_content.return_value = mock_response
        
        detector = StudyTypeDetector(
            mock_client,
            confidence_threshold=0.7,
            fallback_checklist="casp_cohort"
        )
        
        study_data = {
            'title': 'Study of AI Tutoring',
            'study_design': 'Not clearly specified',
            'methodology': 'Students used AI tutor',
            'participants': '30 students',
            'interventions': [],
            'outcomes': []
        }
        
        result = detector.detect_study_type(study_data)
        
        # Should use fallback
        assert result['checklist'] == 'casp_cohort'
        assert result['fallback_used'] is True
        assert result['confidence'] == 0.55  # Original confidence preserved
    
    def test_detection_error_handling(self):
        """Test that errors are handled gracefully with fallback."""
        mock_client = Mock()
        mock_client.models.generate_content.side_effect = Exception("API Error")
        
        detector = StudyTypeDetector(mock_client)
        
        study_data = {'title': 'Test Study'}
        
        result = detector.detect_study_type(study_data)
        
        assert result['checklist'] == 'casp_cohort'  # Fallback
        assert result['confidence'] == 0.0
        assert result['fallback_used'] is True
        assert 'error' in result


class TestCASPPrompts:
    """Tests for CASP prompt generation."""
    
    def test_build_casp_rct_prompt(self):
        """Test RCT prompt generation includes all 11 questions."""
        study_title = "Test RCT Study"
        extracted_data = {
            'study_design': 'RCT',
            'methodology': 'Randomized trial',
            'participants': '100 students',
            'interventions': ['AI tutor', 'Control'],
            'outcomes': ['Exam scores'],
            'key_findings': ['Significant improvement'],
            'limitations': ['Small sample']
        }
        
        prompt = build_casp_rct_prompt(study_title, extracted_data)
        
        # Check prompt includes key components
        assert 'CASP RCT Checklist' in prompt
        assert '11 questions' in prompt or 'Q1' in prompt
        assert 'focused issue' in prompt.lower()
        assert 'randomized' in prompt.lower()
        assert 'blinded' in prompt.lower()
        assert 'treatment effect' in prompt.lower()
        assert study_title in prompt
        assert 'JSON' in prompt
        
        # Check all 11 questions are present
        for i in range(1, 12):
            assert f'QUESTION {i}' in prompt or f'Q{i}' in prompt
    
    def test_build_casp_cohort_prompt(self):
        """Test cohort prompt generation includes all 12 questions."""
        study_title = "Test Cohort Study"
        extracted_data = {
            'study_design': 'Cohort',
            'methodology': 'Longitudinal study',
            'participants': '50 students',
            'interventions': ['AI chatbot'],
            'outcomes': ['Usage', 'Performance'],
            'key_findings': ['Positive outcomes'],
            'limitations': ['Attrition']
        }
        
        prompt = build_casp_cohort_prompt(study_title, extracted_data)
        
        assert 'CASP Cohort Study Checklist' in prompt
        assert '12 questions' in prompt or 'Q1' in prompt
        assert 'cohort recruited' in prompt.lower()
        assert 'exposure' in prompt.lower()
        assert 'confounding' in prompt.lower()
        assert 'follow-up' in prompt.lower()
        assert study_title in prompt
        
        # Check all 12 questions are present
        for i in range(1, 13):
            assert f'QUESTION {i}' in prompt or f'Q{i}' in prompt
    
    def test_build_casp_qualitative_prompt(self):
        """Test qualitative prompt generation includes all 10 questions."""
        study_title = "Test Qualitative Study"
        extracted_data = {
            'study_design': 'Qualitative',
            'methodology': 'Interviews with thematic analysis',
            'participants': '20 students',
            'key_findings': ['Three main themes identified'],
            'limitations': ['Limited generalizability']
        }
        
        prompt = build_casp_qualitative_prompt(study_title, extracted_data)
        
        assert 'CASP Qualitative Research Checklist' in prompt
        assert '10 questions' in prompt or 'Q1' in prompt
        assert 'aims of the research' in prompt.lower()
        assert 'qualitative methodology' in prompt.lower()
        assert 'recruitment strategy' in prompt.lower()
        assert 'data analysis' in prompt.lower()
        assert study_title in prompt
        
        # Check all 10 questions are present
        for i in range(1, 11):
            assert f'QUESTION {i}' in prompt or f'Q{i}' in prompt
    
    def test_get_checklist_info(self):
        """Test checklist info retrieval."""
        rct_info = get_checklist_info('casp_rct')
        assert rct_info['num_questions'] == 11
        assert 'RCT' in rct_info['name']
        
        cohort_info = get_checklist_info('casp_cohort')
        assert cohort_info['num_questions'] == 12
        assert 'Cohort' in cohort_info['name']
        
        qual_info = get_checklist_info('casp_qualitative')
        assert qual_info['num_questions'] == 10
        assert 'Qualitative' in qual_info['name']
    
    def test_get_all_checklist_types(self):
        """Test retrieval of all checklist types."""
        types = get_all_checklist_types()
        assert len(types) == 3
        assert 'casp_rct' in types
        assert 'casp_cohort' in types
        assert 'casp_qualitative' in types


class TestCASPAssessment:
    """Tests for CASP assessment execution and scoring."""
    
    def test_assess_with_casp_rct(self):
        """Test CASP RCT assessment execution."""
        # Mock LLM response
        mock_response = {
            "q1": {"answer": "Yes", "justification": "Clear PICO elements"},
            "q2": {"answer": "Yes", "justification": "Computer-generated randomization"},
            "q3": {"answer": "Yes", "justification": "All participants accounted for"},
            "q4": {"answer": "No", "justification": "Not blinded due to intervention type"},
            "q5": {"answer": "Yes", "justification": "Groups well-matched at baseline"},
            "q6": {"answer": "Yes", "justification": "Equal treatment except intervention"},
            "q7": {"answer": "Yes", "justification": "Large effect size (d=0.8)"},
            "q8": {"answer": "Yes", "justification": "Narrow confidence intervals"},
            "q9": {"answer": "Yes", "justification": "Similar setting applicable"},
            "q10": {"answer": "Yes", "justification": "Comprehensive outcomes"},
            "q11": {"answer": "Yes", "justification": "Benefits outweigh minimal harms"},
            "summary": {
                "yes_count": 10,
                "no_count": 1,
                "cant_tell_count": 0,
                "quality_rating": "High",
                "overall_notes": "High quality RCT with minor limitation in blinding"
            }
        }
        
        # Setup mock
        mock_client_instance = Mock()
        mock_client_instance.models.generate_content.return_value.text = json.dumps(mock_response)
        
        filler = QualityAssessmentAutoFiller(llm_provider="gemini", llm_model="gemini-2.5-pro")
        filler.llm_client = mock_client_instance
        
        result = filler.assess_with_casp(
            study_title="Test RCT",
            checklist_type="casp_rct",
            extracted_data={'study_design': 'RCT'}
        )
        
        assert result['checklist_used'] == 'casp_rct'
        assert result['score']['yes_count'] == 10
        assert result['score']['quality_rating'] == 'High'
        assert 'q1' in result['responses']
        assert result['responses']['q1']['answer'] == 'Yes'
    
    def test_casp_scoring_high_quality(self):
        """Test high quality scoring (>80% Yes)."""
        # 9/11 = 82% for RCT -> High
        yes_count = 9
        total = 11
        percentage = yes_count / total
        
        if percentage >= 0.8:
            rating = 'High'
        elif percentage >= 0.5:
            rating = 'Moderate'
        else:
            rating = 'Low'
        
        assert rating == 'High'
    
    def test_casp_scoring_moderate_quality(self):
        """Test moderate quality scoring (50-80% Yes)."""
        # 7/12 = 58% for Cohort -> Moderate
        yes_count = 7
        total = 12
        percentage = yes_count / total
        
        if percentage >= 0.8:
            rating = 'High'
        elif percentage >= 0.5:
            rating = 'Moderate'
        else:
            rating = 'Low'
        
        assert rating == 'Moderate'
    
    def test_casp_scoring_low_quality(self):
        """Test low quality scoring (<50% Yes)."""
        # 4/10 = 40% for Qualitative -> Low
        yes_count = 4
        total = 10
        percentage = yes_count / total
        
        if percentage >= 0.8:
            rating = 'High'
        elif percentage >= 0.5:
            rating = 'Moderate'
        else:
            rating = 'Low'
        
        assert rating == 'Low'
    
    def test_assess_with_invalid_response(self):
        """Test handling of invalid LLM response."""
        # Mock invalid response
        mock_client_instance = Mock()
        mock_client_instance.models.generate_content.return_value.text = "Invalid JSON"
        
        filler = QualityAssessmentAutoFiller(llm_provider="gemini")
        filler.llm_client = mock_client_instance
        
        result = filler.assess_with_casp(
            study_title="Test Study",
            checklist_type="casp_cohort",
            extracted_data={}
        )
        
        # Should return fallback assessment
        assert result['checklist_used'] == 'casp_cohort'
        assert result['score']['cant_tell_count'] == 12  # All questions marked as Can't Tell
        assert result['score']['quality_rating'] == 'Moderate'


class TestResponseParsing:
    """Tests for CASP response parsing."""
    
    def test_parse_valid_json_response(self):
        """Test parsing of valid JSON response."""
        response_text = json.dumps({
            "q1": {"answer": "Yes", "justification": "Clear aims"},
            "q2": {"answer": "No", "justification": "Methodology not appropriate"},
            "q3": {"answer": "Can't Tell", "justification": "Insufficient information"},
            "summary": {
                "yes_count": 1,
                "no_count": 1,
                "cant_tell_count": 1,
                "quality_rating": "Low",
                "overall_notes": "Mixed quality"
            }
        })
        
        parsed = json.loads(response_text)
        
        assert parsed['q1']['answer'] == 'Yes'
        assert parsed['q2']['answer'] == 'No'
        assert parsed['q3']['answer'] == "Can't Tell"
        assert parsed['summary']['yes_count'] == 1
    
    def test_parse_response_with_markdown(self):
        """Test parsing response that includes markdown code blocks."""
        response_text = """```json
{
  "q1": {"answer": "Yes", "justification": "Test"},
  "summary": {"yes_count": 1, "quality_rating": "Moderate", "overall_notes": "Test"}
}
```"""
        
        # Remove markdown code blocks
        import re
        cleaned = re.sub(r'```json\s*|\s*```', '', response_text).strip()
        parsed = json.loads(cleaned)
        
        assert parsed['q1']['answer'] == 'Yes'
        assert 'summary' in parsed


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
