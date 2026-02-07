"""
CASP (Critical Appraisal Skills Programme) checklist prompts.

Comprehensive prompts for each CASP checklist with detailed criteria,
examples, and scoring guidance for LLM-based quality assessment.
"""

from typing import Dict, Any


def build_casp_rct_prompt(
    study_title: str,
    extracted_data: Dict[str, Any]
) -> str:
    """
    Build comprehensive CASP RCT Checklist prompt.
    
    CASP RCT Checklist: 11 questions organized in 3 sections
    - Section A: Validity (Q1-3)
    - Section B: Results (Q4-7)
    - Section C: Applicability (Q8-11)
    
    Args:
        study_title: Title of the study being assessed
        extracted_data: Dictionary with extracted study information
        
    Returns:
        Comprehensive prompt string for LLM assessment
    """
    # Extract relevant fields
    study_design = extracted_data.get('study_design', 'Not specified')
    methodology = extracted_data.get('methodology', 'Not specified')
    participants = extracted_data.get('participants', 'Not specified')
    interventions = extracted_data.get('interventions', [])
    outcomes = extracted_data.get('outcomes', [])
    key_findings = extracted_data.get('key_findings', [])
    limitations = extracted_data.get('limitations', [])
    
    interventions_str = '\n'.join(f"- {i}" for i in interventions) if interventions else "Not specified"
    outcomes_str = '\n'.join(f"- {o}" for o in outcomes) if outcomes else "Not specified"
    findings_str = '\n'.join(f"- {f}" for f in key_findings) if key_findings else "Not specified"
    limitations_str = '\n'.join(f"- {lim}" for lim in limitations) if limitations else "Not specified"
    
    prompt = f"""You are conducting quality assessment using the CASP RCT Checklist (Randomized Controlled Trial).

ABOUT CASP RCT CHECKLIST:
The CASP RCT Checklist is a validated tool for critically appraising randomized controlled trials.
It contains 11 questions organized into 3 sections: Validity (Q1-3), Results (Q4-7), and Applicability (Q8-11).
This tool is used worldwide for systematic reviews in healthcare, education, and social sciences.

STUDY TO ASSESS:
Title: {study_title}
Design: {study_design}

Methodology:
{methodology}

Participants:
{participants}

Interventions:
{interventions_str}

Outcomes:
{outcomes_str}

Key Findings:
{findings_str}

Limitations:
{limitations_str}

================================================================================
INSTRUCTIONS:
Answer each question with: "Yes" OR "No" OR "Can't Tell"
Provide a 1-3 sentence justification citing specific evidence from the study.
Be objective and evidence-based in your assessment.
================================================================================

SECTION A: ARE THE RESULTS VALID?

QUESTION 1: Did the trial address a clearly focused issue?

CRITERIA FOR "YES":
- The study has a clear, specific research question
- PICO elements are well-defined:
  * Population: Specific, well-defined participant group
  * Intervention: Clearly described treatment/technology being tested
  * Comparison: Explicit control or comparison group
  * Outcome: Specific, measurable outcomes stated upfront
- The research objective is answerable and appropriately scoped

CRITERIA FOR "NO":
- Research question is vague, too broad, or poorly defined
- Multiple unfocused objectives without clear priority
- PICO elements are unclear, missing, or contradictory
- The study tries to answer too many unrelated questions

CRITERIA FOR "CAN'T TELL":
- Some PICO elements are present but not all clearly stated
- Question is somewhat focused but could be more specific
- Sufficient information not available in the extracted data

WHAT TO LOOK FOR:
- Introduction/aims section for research question statement
- Methods section for PICO specification
- Abstract for clear study purpose
- Objective statements in methodology

EXAMPLE "YES": "To determine whether a 12-week conversational AI tutoring intervention improves anatomy exam scores by >10% compared to standard textbook study among first-year medical students"

EXAMPLE "NO": "To explore the use of AI in healthcare education and examine various factors"

Your Answer for Q1:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence from the study]

---

QUESTION 2: Was the assignment of patients to treatments randomized?

CRITERIA FOR "YES":
- Clear statement that participants were randomly allocated to groups
- Explicit mention of randomization method (computer-generated, random number table, etc.)
- Use of terms like "randomly assigned", "random allocation", "randomization"
- Description of random sequence generation process

CRITERIA FOR "NO":
- Non-random allocation (alternation, date of birth, case number, patient preference)
- Quasi-experimental design without randomization
- Explicit statement that randomization was not used
- Allocation based on convenience or systematic methods

CRITERIA FOR "CAN'T TELL":
- Study claims to be randomized but provides no details on method
- Unclear whether allocation was truly random
- Conflicting information about randomization
- Term "randomized" used but mechanism not described

WHAT TO LOOK FOR:
- Methods section for randomization procedure
- Flowchart or participant allocation description
- Statistical methods mentioning randomization
- Study design explicitly stating "RCT" or "randomized trial"

IMPORTANT: Many studies claim to be "trials" or "experiments" but are NOT randomized. Look for explicit randomization language.

Your Answer for Q2:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about randomization]

---

QUESTION 3: Were all patients who entered the trial properly accounted for at its conclusion?

CRITERIA FOR "YES":
- >95% of randomized participants included in analysis
- Clear participant flowchart showing all randomized patients
- Minimal dropout with clear reporting of all losses
- Intention-to-treat (ITT) analysis conducted
- All exclusions and losses explained with numbers

CRITERIA FOR "NO":
- >20% dropout or loss to follow-up without explanation
- Participants excluded from analysis without clear justification
- No flowchart or unclear accounting of participants
- Per-protocol analysis only, excluding non-completers
- Substantial imbalance in losses between groups

CRITERIA FOR "CAN'T TELL":
- Dropout rate between 5-20% with partial explanation
- Some accounting provided but not complete
- Unclear whether ITT or per-protocol analysis used
- Participant flow diagram missing or incomplete

WHAT TO LOOK FOR:
- CONSORT flow diagram or participant tracking
- Results section reporting how many participants analyzed
- Discussion of dropout, withdrawal, or loss to follow-up
- Statement about ITT or modified ITT analysis

Your Answer for Q3:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about participant accounting]

---

SECTION B: WHAT ARE THE RESULTS?

QUESTION 4: Were patients, health workers and study personnel blinded to treatment?

CRITERIA FOR "YES":
- Double-blind or triple-blind design described
- Participants unaware of their assigned intervention
- Healthcare providers/educators unaware of assignments
- Outcome assessors blinded to group allocation
- Effective blinding procedures described

CRITERIA FOR "NO":
- Open-label study (no blinding)
- Participants and/or personnel aware of treatment assignment
- Blinding not attempted or explicitly stated as impossible
- Study design prevents blinding (e.g., behavioral interventions)

CRITERIA FOR "CAN'T TELL":
- Blinding mentioned but unclear who was blinded
- Claims of blinding but no description of how it was maintained
- Partial blinding (only some parties blinded)
- Insufficient information about blinding procedures

WHAT TO LOOK FOR:
- Methods section describing masking/blinding procedures
- Terms: "double-blind", "single-blind", "masked", "concealed allocation"
- Discussion of whether blinding was feasible given intervention type
- Note: For many behavioral/educational interventions, blinding is impossible - this doesn't automatically mean high bias

Your Answer for Q4:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about blinding, note if blinding was impossible due to intervention type]

---

QUESTION 5: Were the groups similar at the start of the trial?

CRITERIA FOR "YES":
- Baseline characteristics table shows groups are well-matched
- No statistically significant differences in key prognostic factors
- Groups balanced on demographics, disease severity, or baseline measures
- Standardized mean differences <0.2 for important variables
- Any minor imbalances unlikely to affect results

CRITERIA FOR "NO":
- Important baseline differences between groups (p<0.05)
- Groups differ on key prognostic factors (age, severity, baseline outcome)
- Imbalances suggest randomization may have failed
- Systematic differences favoring one group

CRITERIA FOR "CAN'T TELL":
- Baseline characteristics not reported or incompletely reported
- Some characteristics reported but key confounders missing
- Unclear whether differences are clinically meaningful
- Statistical testing of baseline differences not provided

WHAT TO LOOK FOR:
- Table 1 or baseline characteristics table
- Methods describing what baseline variables were measured
- Results reporting group comparisons at baseline
- Discussion acknowledging any imbalances

Your Answer for Q5:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about baseline comparability]

---

QUESTION 6: Aside from the experimental intervention, were the groups treated equally?

CRITERIA FOR "YES":
- All co-interventions, procedures, and care were identical between groups
- Follow-up schedules and assessments were the same
- No differential treatment beyond the intervention of interest
- Protocol violations were minimal and balanced
- Contamination between groups was prevented or minimal

CRITERIA FOR "NO":
- Groups received different co-interventions or care
- Unequal access to additional treatments or resources
- Different follow-up procedures or assessment schedules
- Significant protocol deviations in one group
- Crossover or contamination between groups

CRITERIA FOR "CAN'T TELL":
- Insufficient information about co-interventions
- Unclear whether groups had equal access to care
- Protocol deviations mentioned but not quantified
- Unclear whether differences in treatment existed

WHAT TO LOOK FOR:
- Methods describing what was standardized across groups
- Results reporting protocol adherence or deviations
- Discussion of co-interventions or contamination
- Description of care provided to control group

Your Answer for Q6:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about equal treatment]

---

QUESTION 7: How large was the treatment effect?

CRITERIA FOR "YES" (Large/Meaningful Effect):
- Clinically or educationally meaningful difference between groups
- Effect size is substantial (Cohen's d >0.5, or >10% absolute difference)
- Statistical significance achieved (p<0.05) with meaningful magnitude
- Results show clear benefit on primary outcomes
- Effect size is reported and substantial

CRITERIA FOR "NO" (Small/Negligible Effect):
- Difference between groups is trivial or not meaningful
- Effect size is small (Cohen's d <0.2, or <5% absolute difference)
- No statistical significance or p-values near 1.0
- Results show no clear benefit

CRITERIA FOR "CAN'T TELL":
- Effect size not clearly reported
- Statistical significance achieved but clinical/practical significance unclear
- Mixed results across outcomes
- Insufficient data to judge magnitude

WHAT TO LOOK FOR:
- Results section reporting primary outcome differences
- Effect sizes, mean differences, relative risks, odds ratios
- Statistical significance (p-values, confidence intervals)
- Discussion of clinical/practical significance

Your Answer for Q7:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific effect sizes or outcome differences]

---

SECTION C: WILL THE RESULTS HELP LOCALLY?

QUESTION 8: How precise was the estimate of the treatment effect?

CRITERIA FOR "YES" (Precise):
- Confidence intervals are narrow
- Large sample size provides good statistical power
- Standard errors are small relative to effect size
- Results are consistent and stable
- P-values well below 0.05 (if significant) or clearly non-significant

CRITERIA FOR "NO" (Imprecise):
- Wide confidence intervals crossing null effect
- Small sample size resulting in low power
- Large standard errors relative to effect size
- Borderline statistical significance (p near 0.05)
- Results suggest high uncertainty

CRITERIA FOR "CAN'T TELL":
- Confidence intervals not reported
- Sample size reported but power not discussed
- Statistical precision unclear from available data
- Mixed precision across different outcomes

WHAT TO LOOK FOR:
- Confidence intervals (95% CI) around effect estimates
- Sample size and power calculations
- Standard errors or standard deviations
- Discussion of statistical power or precision

Your Answer for Q8:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about precision]

---

QUESTION 9: Can the results be applied to your local population or in your context?

CRITERIA FOR "YES":
- Study population is similar to target population
- Setting is comparable or findings are generalizable
- Intervention is feasible and practical in similar contexts
- No major barriers to implementation
- Results are likely to transfer to other similar settings

CRITERIA FOR "NO":
- Study population differs substantially (age, severity, context)
- Setting is highly specialized or unique
- Intervention requires resources/expertise not widely available
- Cultural, geographic, or system differences limit applicability
- Results may not generalize beyond the specific study context

CRITERIA FOR "CAN'T TELL":
- Insufficient description of study setting or population
- Generalizability not discussed
- Unclear whether intervention is feasible elsewhere
- Some similarities but important differences

WHAT TO LOOK FOR:
- Participant demographics and selection criteria
- Study setting description (country, institution type, resources)
- Discussion section addressing generalizability or external validity
- Practical considerations for implementation

NOTE: Consider YOUR context - if this is a systematic review, consider whether results apply to the broader research question rather than a specific local setting.

Your Answer for Q9:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about applicability]

---

QUESTION 10: Were all clinically important outcomes considered?

CRITERIA FOR "YES":
- Primary outcomes are relevant and important
- Secondary outcomes cover key domains of interest
- Both benefits and harms are assessed
- Patient-relevant outcomes included (not just surrogate markers)
- Outcome selection is comprehensive and appropriate

CRITERIA FOR "NO":
- Important outcomes are missing (e.g., only measures benefits, ignores harms)
- Focus on surrogate outcomes when direct outcomes are feasible
- Selective outcome reporting (some outcomes not reported)
- Outcome selection appears incomplete or biased

CRITERIA FOR "CAN'T TELL":
- Unclear whether all important outcomes were measured
- Outcome selection rationale not provided
- Some outcomes mentioned in methods but not reported in results
- Insufficient information about adverse events or harms

WHAT TO LOOK FOR:
- Methods section listing primary and secondary outcomes
- Results reporting all pre-specified outcomes
- Discussion of adverse events, side effects, or harms
- Comparison with other studies' outcome choices

NOTE: "Clinically important" can be interpreted as "practically important" or "educationally important" depending on the study domain.

Your Answer for Q10:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about outcome comprehensiveness]

---

QUESTION 11: Are the benefits worth the harms and costs?

CRITERIA FOR "YES":
- Clear evidence that benefits outweigh harms
- Cost considerations discussed (if relevant)
- Risk-benefit ratio is favorable
- Discussion acknowledges trade-offs and concludes benefits justify use
- Practical implications suggest worthwhile intervention

CRITERIA FOR "NO":
- Harms equal or exceed benefits
- Costs are prohibitive relative to benefits
- Risk-benefit ratio is unfavorable
- Authors acknowledge limited practical value
- Significant barriers to implementation outweigh benefits

CRITERIA FOR "CAN'T TELL":
- Insufficient information about harms or adverse events
- Costs not discussed when relevant
- Trade-offs not explicitly discussed
- Authors don't comment on overall value
- Benefits and harms are mixed or unclear

WHAT TO LOOK FOR:
- Discussion section weighing benefits vs harms
- Cost-effectiveness analysis or discussion
- Practical implications or recommendations
- Authors' conclusions about implementation
- Adverse events reporting

NOTE: This is a holistic judgment question. Consider the overall value of the intervention.

Your Answer for Q11:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about benefit-harm-cost balance]

================================================================================
SCORING AND OVERALL ASSESSMENT:
================================================================================

After answering all 11 questions:
1. Count the number of "Yes" responses
2. Assign overall quality rating:
   - High Quality: 9-11 "Yes" responses (>80%)
   - Moderate Quality: 5-8 "Yes" responses (50-80%)
   - Low Quality: 0-4 "Yes" responses (<50%)

3. Provide overall summary (2-3 sentences) highlighting:
   - Main strengths of the study
   - Main limitations or concerns
   - Overall quality judgment

================================================================================
RESPONSE FORMAT:
================================================================================

Return your assessment as valid JSON only (no markdown, no code blocks):

{{
  "q1": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q2": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q3": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q4": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q5": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q6": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q7": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q8": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q9": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q10": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q11": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "summary": {{
    "yes_count": [number],
    "no_count": [number],
    "cant_tell_count": [number],
    "quality_rating": "High/Moderate/Low",
    "overall_notes": "2-3 sentence summary of main strengths and limitations"
  }}
}}

Respond with JSON only:"""
    
    return prompt


def build_casp_cohort_prompt(
    study_title: str,
    extracted_data: Dict[str, Any]
) -> str:
    """
    Build comprehensive CASP Cohort Study Checklist prompt.
    
    CASP Cohort Checklist: 12 questions organized in 3 sections
    - Section A: Validity (Q1-6)
    - Section B: Results (Q7-9)
    - Section C: Applicability (Q10-12)
    
    Args:
        study_title: Title of the study being assessed
        extracted_data: Dictionary with extracted study information
        
    Returns:
        Comprehensive prompt string for LLM assessment
    """
    study_design = extracted_data.get('study_design', 'Not specified')
    methodology = extracted_data.get('methodology', 'Not specified')
    participants = extracted_data.get('participants', 'Not specified')
    interventions = extracted_data.get('interventions', [])
    outcomes = extracted_data.get('outcomes', [])
    key_findings = extracted_data.get('key_findings', [])
    limitations = extracted_data.get('limitations', [])
    
    interventions_str = '\n'.join(f"- {i}" for i in interventions) if interventions else "Not specified"
    outcomes_str = '\n'.join(f"- {o}" for o in outcomes) if outcomes else "Not specified"
    findings_str = '\n'.join(f"- {f}" for f in key_findings) if key_findings else "Not specified"
    limitations_str = '\n'.join(f"- {lim}" for lim in limitations) if limitations else "Not specified"
    
    prompt = f"""You are conducting quality assessment using the CASP Cohort Study Checklist.

ABOUT CASP COHORT CHECKLIST:
The CASP Cohort Study Checklist is a validated tool for critically appraising observational cohort studies.
It contains 12 questions organized into 3 sections: Validity (Q1-6), Results (Q7-9), and Applicability (Q10-12).
Cohort studies follow groups of people over time to examine exposures and outcomes without random assignment.

STUDY TO ASSESS:
Title: {study_title}
Design: {study_design}

Methodology:
{methodology}

Participants:
{participants}

Interventions/Exposures:
{interventions_str}

Outcomes:
{outcomes_str}

Key Findings:
{findings_str}

Limitations:
{limitations_str}

================================================================================
INSTRUCTIONS:
Answer each question with: "Yes" OR "No" OR "Can't Tell"
Provide a 1-3 sentence justification citing specific evidence from the study.
================================================================================

SECTION A: ARE THE RESULTS VALID?

QUESTION 1: Did the study address a clearly focused issue?

CRITERIA FOR "YES":
- Clear research question about exposure and outcome relationship
- Well-defined cohort selection criteria
- Specific exposure/intervention being examined
- Defined outcome(s) of interest
- Appropriate research design for the question

CRITERIA FOR "NO":
- Vague or unfocused research question
- Poorly defined cohort or selection criteria
- Multiple unfocused objectives
- Exposure or outcome not clearly specified

CRITERIA FOR "CAN'T TELL":
- Question is somewhat clear but could be more specific
- Some elements defined but not all
- Insufficient information in extracted data

WHAT TO LOOK FOR:
- Study aims and objectives
- Cohort definition and selection criteria
- Clear exposure-outcome relationship being investigated

Your Answer for Q1:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence]

---

QUESTION 2: Was the cohort recruited in an acceptable way?

CRITERIA FOR "YES":
- Recruitment method minimizes selection bias
- Cohort is representative of the target population
- Clear inclusion/exclusion criteria applied consistently
- Sampling strategy is appropriate
- Recruitment process is well-documented

CRITERIA FOR "NO":
- Convenience sampling without justification
- Self-selected or volunteer cohort with likely bias
- Recruitment method introduces systematic bias
- Inclusion criteria are unclear or inconsistently applied
- Cohort is not representative of any defined population

CRITERIA FOR "CAN'T TELL":
- Recruitment method not clearly described
- Unclear whether cohort is representative
- Some information provided but key details missing
- Sampling strategy unclear

WHAT TO LOOK FOR:
- Methods describing recruitment procedures
- Sampling strategy (random, consecutive, convenience)
- Response rate or participation rate
- Description of how participants were identified and enrolled

Your Answer for Q2:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about recruitment]

---

QUESTION 3: Was the exposure accurately measured to minimize bias?

CRITERIA FOR "YES":
- Valid and reliable measurement method for exposure
- Consistent measurement across all participants
- Objective measures used when possible
- Measurement occurred before outcome
- Exposure assessment unlikely to be influenced by outcome

CRITERIA FOR "NO":
- Exposure measured after outcome (reverse causation possible)
- Measurement method has poor validity or reliability
- Exposure self-reported with high potential for bias
- Differential measurement between groups
- Unclear timing of exposure measurement

CRITERIA FOR "CAN'T TELL":
- Exposure measurement method not clearly described
- Validity/reliability of measure unclear
- Timing of measurement relative to outcome unclear
- Insufficient information about measurement procedures

WHAT TO LOOK FOR:
- Methods describing how exposure was measured
- Validation of exposure measurement tool
- Timing of exposure assessment
- Whether exposure was objectively measured

NOTE: In technology implementation studies, "exposure" may be technology use/adoption.

Your Answer for Q3:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about exposure measurement]

---

QUESTION 4: Was the outcome accurately measured to minimize bias?

CRITERIA FOR "YES":
- Valid and reliable outcome measurement instrument
- Standardized measurement across all participants
- Assessors blinded to exposure status (when possible)
- Objective outcome measures used when feasible
- Consistent follow-up schedule for outcome assessment

CRITERIA FOR "NO":
- Outcome measure has poor validity or reliability
- Differential measurement between exposure groups
- Assessors aware of exposure (when blinding is feasible)
- Inconsistent or incomplete outcome assessment
- Subjective measures without validation

CRITERIA FOR "CAN'T TELL":
- Outcome measurement method not clearly described
- Validity/reliability unclear
- Blinding status unclear
- Insufficient information about measurement procedures

WHAT TO LOOK FOR:
- Description of outcome measurement tools/instruments
- Validation studies for outcome measures
- Blinding of outcome assessors
- Standardization of measurement procedures

Your Answer for Q4:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about outcome measurement]

---

QUESTION 5: Have the authors identified all important confounding factors?

CRITERIA FOR "YES":
- Comprehensive list of potential confounders identified
- Known prognostic factors are considered
- Confounders are measured and reported
- Authors demonstrate understanding of confounding
- Key demographic, clinical, or contextual factors included

CRITERIA FOR "NO":
- Important confounders not identified or measured
- Authors don't discuss confounding
- Only crude analysis without confounder consideration
- Known risk factors for outcome are ignored
- Confounding variables not measured

CRITERIA FOR "CAN'T TELL":
- Some confounders identified but unclear if comprehensive
- Confounders measured but not all reported
- Unclear what was considered as potential confounders
- Partial information about confounding factors

WHAT TO LOOK FOR:
- Methods listing variables measured
- Statistical analysis plan mentioning confounders
- Table 1 showing baseline characteristics
- Discussion of confounding factors

IMPORTANT: For observational studies, controlling for confounding is critical.

Your Answer for Q5:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific confounders that were or were not considered]

---

QUESTION 6: Have the authors taken account of confounding factors in the design and/or analysis?

CRITERIA FOR "YES":
- Multivariable analysis adjusting for confounders
- Matching, stratification, or restriction used in design
- Propensity score methods, inverse probability weighting, or other advanced methods
- Adjusted effect estimates reported
- Sensitivity analyses examining confounding

CRITERIA FOR "NO":
- Only crude, unadjusted analysis presented
- Confounders identified but not controlled for
- Statistical methods don't address confounding
- No adjustment in design or analysis
- Confounding acknowledged but not handled

CRITERIA FOR "CAN'T TELL":
- Statistical methods not clearly described
- Unclear whether analysis is adjusted or unadjusted
- Some adjustment mentioned but methods unclear
- Insufficient information about analytical approach

WHAT TO LOOK FOR:
- Statistical methods mentioning regression, adjustment, or matching
- Results showing both crude and adjusted estimates
- Description of multivariable models
- Sensitivity analyses

Your Answer for Q6:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about confounder control]

---

SECTION B: WHAT ARE THE RESULTS?

QUESTION 7: Was the follow-up of subjects complete enough?

CRITERIA FOR "YES":
- >80% of cohort completed follow-up
- Loss to follow-up is minimal and well-documented
- Dropout rates are similar between exposure groups
- Reasons for loss to follow-up are provided
- Complete case analysis is justified

CRITERIA FOR "NO":
- >30% loss to follow-up without explanation
- Differential dropout between exposure groups
- High attrition rate suggesting selection bias
- Reasons for dropout related to outcome
- Missing data not addressed

CRITERIA FOR "CAN'T TELL":
- Follow-up rates not clearly reported
- Loss to follow-up mentioned but not quantified
- Unclear whether dropout differs between groups
- Moderate attrition (20-30%) with partial explanation

WHAT TO LOOK FOR:
- Results reporting retention rates or loss to follow-up
- Flow diagram showing participant progression
- Discussion of attrition or missing data
- Comparison of dropout between exposure groups

Your Answer for Q7:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about follow-up completeness]

---

QUESTION 8: Was the follow-up of subjects long enough?

CRITERIA FOR "YES":
- Follow-up duration is sufficient for outcome to occur
- Time period appropriate for research question
- Long enough to detect meaningful effects
- Follow-up aligns with clinical/practical relevance
- Multiple time points assessed if appropriate

CRITERIA FOR "NO":
- Follow-up too short for outcome to manifest
- Key outcomes may occur after study ends
- Time period insufficient for research question
- Important late effects not captured

CRITERIA FOR "CAN'T TELL":
- Follow-up duration not clearly reported
- Unclear whether duration is adequate
- Variable follow-up times not explained
- Insufficient information about timing

WHAT TO LOOK FOR:
- Methods describing follow-up duration
- Results reporting assessment time points
- Discussion of whether timing was adequate
- Comparison with other studies' follow-up periods

Your Answer for Q8:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about follow-up duration]

---

QUESTION 9: What are the results of this study?

CRITERIA FOR "YES" (Clear and Important Results):
- Effect sizes and confidence intervals clearly reported
- Statistical significance is clear
- Results are precisely estimated
- Findings are clinically/practically meaningful
- Results answer the research question

CRITERIA FOR "NO" (Unclear or Unimportant Results):
- Results are not clearly reported
- Effect estimates missing or unclear
- Findings don't address research question
- Statistical analysis is inadequate
- Results lack practical significance

CRITERIA FOR "CAN'T TELL":
- Results partially reported
- Some outcomes reported but not all
- Statistical presentation is confusing
- Insufficient detail in results section

WHAT TO LOOK FOR:
- Results section with effect estimates
- Tables and figures presenting outcomes
- Statistical significance testing
- Clinical/practical significance discussion

Your Answer for Q9:
- Answer: [Yes/No/Can't Tell]
- Justification: [Summarize key results with specific numbers/findings]

---

SECTION C: WILL THE RESULTS HELP LOCALLY?

QUESTION 10: How precise are the results?

CRITERIA FOR "YES":
- Narrow confidence intervals
- Sufficient sample size
- Precise effect estimates
- Low standard errors
- Results are stable and reliable

CRITERIA FOR "NO":
- Wide confidence intervals crossing null
- Small sample size limiting precision
- Large standard errors
- Unstable or unreliable estimates
- High uncertainty in findings

CRITERIA FOR "CAN'T TELL":
- Confidence intervals not reported
- Precision not discussed
- Sample size adequate but precision unclear
- Mixed precision across outcomes

WHAT TO LOOK FOR:
- Confidence intervals around effect estimates
- Sample size and power discussion
- Standard errors or standard deviations
- Statistical precision indicators

Your Answer for Q10:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about precision]

---

QUESTION 11: Do you believe the results?

CRITERIA FOR "YES":
- Study design is sound and appropriate
- Analysis methods are valid
- Results are plausible and consistent
- Confounding adequately addressed
- Bias risks are minimal or well-managed
- Results align with existing evidence

CRITERIA FOR "NO":
- Major methodological flaws present
- Results implausible or contradictory
- Inadequate handling of bias or confounding
- Analysis methods questionable
- Results contradict well-established findings without explanation

CRITERIA FOR "CAN'T TELL":
- Mixed quality with both strengths and weaknesses
- Some concerns but not fatal flaws
- Results are plausible but methods have limitations
- Moderate confidence in findings

WHAT TO LOOK FOR:
- Overall methodological rigor
- Consistency of findings
- Authors' discussion of limitations
- Plausibility of results

NOTE: This is a holistic judgment based on all previous questions.

Your Answer for Q11:
- Answer: [Yes/No/Can't Tell]
- Justification: [Provide holistic assessment]

---

QUESTION 12: Can the results be applied to the local population?

CRITERIA FOR "YES":
- Study population similar to target population
- Setting is comparable or generalizable
- Exposure/intervention is feasible in other contexts
- Results likely applicable to similar settings
- No major barriers to generalization

CRITERIA FOR "NO":
- Study population substantially different
- Highly specialized or unique setting
- Exposure/intervention not feasible elsewhere
- Major contextual differences limit applicability
- Results specific to study context

CRITERIA FOR "CAN'T TELL":
- Population or setting not fully described
- Generalizability not discussed
- Some similarities but important differences
- Unclear applicability

WHAT TO LOOK FOR:
- Participant characteristics and selection
- Study setting description
- Discussion of generalizability
- External validity considerations

Your Answer for Q12:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about applicability]

================================================================================
SCORING AND OVERALL ASSESSMENT:
================================================================================

After answering all 12 questions:
1. Count the number of "Yes" responses
2. Assign overall quality rating:
   - High Quality: 10-12 "Yes" responses (>80%)
   - Moderate Quality: 6-9 "Yes" responses (50-80%)
   - Low Quality: 0-5 "Yes" responses (<50%)

3. Provide overall summary (2-3 sentences)

================================================================================
RESPONSE FORMAT:
================================================================================

Return your assessment as valid JSON only (no markdown, no code blocks):

{{
  "q1": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q2": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q3": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q4": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q5": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q6": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q7": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q8": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q9": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q10": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q11": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q12": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "summary": {{
    "yes_count": [number],
    "no_count": [number],
    "cant_tell_count": [number],
    "quality_rating": "High/Moderate/Low",
    "overall_notes": "2-3 sentence summary"
  }}
}}

Respond with JSON only:"""
    
    return prompt


def build_casp_qualitative_prompt(
    study_title: str,
    extracted_data: Dict[str, Any]
) -> str:
    """
    Build comprehensive CASP Qualitative Research Checklist prompt.
    
    CASP Qualitative Checklist: 10 questions organized in 3 sections
    - Section A: Validity (Q1-6)
    - Section B: Results (Q7-8)
    - Section C: Value (Q9-10)
    
    Args:
        study_title: Title of the study being assessed
        extracted_data: Dictionary with extracted study information
        
    Returns:
        Comprehensive prompt string for LLM assessment
    """
    study_design = extracted_data.get('study_design', 'Not specified')
    methodology = extracted_data.get('methodology', 'Not specified')
    participants = extracted_data.get('participants', 'Not specified')
    key_findings = extracted_data.get('key_findings', [])
    limitations = extracted_data.get('limitations', [])
    
    findings_str = '\n'.join(f"- {f}" for f in key_findings) if key_findings else "Not specified"
    limitations_str = '\n'.join(f"- {lim}" for lim in limitations) if limitations else "Not specified"
    
    prompt = f"""You are conducting quality assessment using the CASP Qualitative Research Checklist.

ABOUT CASP QUALITATIVE CHECKLIST:
The CASP Qualitative Research Checklist is a validated tool for critically appraising qualitative studies.
It contains 10 questions organized into 3 sections: Validity (Q1-6), Results (Q7-8), and Value (Q9-10).
Qualitative research explores meanings, experiences, and perspectives using interviews, observations, or text analysis.

STUDY TO ASSESS:
Title: {study_title}
Design: {study_design}

Methodology:
{methodology}

Participants:
{participants}

Key Findings:
{findings_str}

Limitations:
{limitations_str}

================================================================================
INSTRUCTIONS:
Answer each question with: "Yes" OR "No" OR "Can't Tell"
Provide a 1-3 sentence justification citing specific evidence from the study.
================================================================================

SECTION A: ARE THE RESULTS VALID?

QUESTION 1: Was there a clear statement of the aims of the research?

CRITERIA FOR "YES":
- Research aims/objectives clearly stated
- Purpose of the study is explicit and focused
- Research question appropriate for qualitative approach
- Goals are specific and well-defined
- Context and significance are explained

CRITERIA FOR "NO":
- Aims are vague or poorly articulated
- Purpose is unclear or unfocused
- Multiple contradictory objectives
- Research question not stated
- Unclear why the study was conducted

CRITERIA FOR "CAN'T TELL":
- Aims mentioned but not clearly articulated
- Some objectives stated but others unclear
- Purpose can be inferred but not explicitly stated
- Insufficient information in extracted data

WHAT TO LOOK FOR:
- Introduction/aims section
- Research questions or objectives
- Statement of study purpose
- Rationale for the research

Your Answer for Q1:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence]

---

QUESTION 2: Is a qualitative methodology appropriate?

CRITERIA FOR "YES":
- Research seeks to explore meanings, experiences, or perspectives
- Questions of "how" or "why" rather than "how many"
- Aims to understand context, processes, or phenomena in depth
- Qualitative approach is well-suited to research aims
- Justification for qualitative approach provided

CRITERIA FOR "NO":
- Research question better suited to quantitative methods
- Aims to measure prevalence or test hypotheses statistically
- Quantitative methods would be more appropriate
- No justification for qualitative approach
- Mismatch between aims and methodology

CRITERIA FOR "CAN'T TELL":
- Could use either qualitative or quantitative approaches
- Rationale for methodology choice not provided
- Mixed methods might be more appropriate
- Unclear whether qualitative approach fits aims

WHAT TO LOOK FOR:
- Justification for qualitative methodology
- Nature of research questions
- Alignment between aims and methods
- Discussion of why qualitative approach was chosen

Your Answer for Q2:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about methodology appropriateness]

---

QUESTION 3: Was the research design appropriate to address the aims of the research?

CRITERIA FOR "YES":
- Study design clearly matches research aims
- Appropriate qualitative approach (phenomenology, grounded theory, ethnography, case study, etc.)
- Data collection methods suit the research question
- Design is well-justified and explained
- Coherence between aims, methods, and design

CRITERIA FOR "NO":
- Design does not match stated aims
- Inappropriate qualitative approach for research question
- Methods don't align with stated methodology
- Design flaws that undermine aims
- Poor fit between design and objectives

CRITERIA FOR "CAN'T TELL":
- Research design not clearly described
- Approach is partially appropriate
- Some alignment but also inconsistencies
- Insufficient information about design

WHAT TO LOOK FOR:
- Methods section describing research design
- Specific qualitative approach identified
- Justification for design choices
- Consistency between aims and design

Your Answer for Q3:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about research design]

---

QUESTION 4: Was the recruitment strategy appropriate to the aims of the research?

CRITERIA FOR "YES":
- Recruitment method appropriate for qualitative inquiry
- Purposive or theoretical sampling used appropriately
- Participant selection aligns with research aims
- Recruitment strategy is clearly explained
- Sufficient diversity or specificity in sample

CRITERIA FOR "NO":
- Convenience sampling without justification
- Recruitment method introduces bias
- Sample selection doesn't match research aims
- Inappropriate sampling for qualitative research
- No explanation of recruitment strategy

CRITERIA FOR "CAN'T TELL":
- Recruitment strategy not clearly described
- Sampling method mentioned but not justified
- Unclear whether strategy fits aims
- Partial information about recruitment

WHAT TO LOOK FOR:
- Description of sampling strategy (purposive, snowball, maximum variation, etc.)
- Recruitment procedures and criteria
- Justification for sampling approach
- Discussion of sample selection

Your Answer for Q4:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about recruitment]

---

QUESTION 5: Was the data collected in a way that addressed the research issue?

CRITERIA FOR "YES":
- Data collection methods appropriate for aims (interviews, focus groups, observations, etc.)
- Setting and context of data collection justified
- Data collection procedure clearly described
- Methods generate rich, detailed data
- Saturation discussed or data sufficiency addressed

CRITERIA FOR "NO":
- Data collection methods inappropriate for aims
- Insufficient detail about procedures
- Setting or context inappropriate
- Data quality appears poor or superficial
- Methods unlikely to address research question

CRITERIA FOR "CAN'T TELL":
- Data collection methods partially described
- Some procedures appropriate but others unclear
- Setting/context not fully explained
- Mixed quality in data collection approach

WHAT TO LOOK FOR:
- Methods describing interview guides, observation protocols, etc.
- Setting and context of data collection
- Discussion of data saturation
- Examples of data or quotes provided

Your Answer for Q5:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about data collection]

---

QUESTION 6: Has the relationship between researcher and participants been adequately considered?

CRITERIA FOR "YES":
- Researcher reflexivity discussed
- Potential for researcher bias acknowledged
- Relationship between researcher and participants examined
- Power dynamics or influence considered
- Steps taken to minimize researcher bias described

CRITERIA FOR "NO":
- No discussion of researcher influence
- Reflexivity absent
- Researcher bias not acknowledged
- Power dynamics ignored
- Objectivity assumed without reflection

CRITERIA FOR "CAN'T TELL":
- Limited discussion of researcher-participant relationship
- Reflexivity mentioned briefly but not thoroughly
- Some awareness but incomplete discussion
- Insufficient information about researcher role

WHAT TO LOOK FOR:
- Reflexivity statements
- Discussion of researcher background or positioning
- Acknowledgment of potential bias
- Methods to ensure rigor and trustworthiness

Your Answer for Q6:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about researcher-participant relationship]

---

SECTION B: WHAT ARE THE RESULTS?

QUESTION 7: Have ethical issues been taken into consideration?

CRITERIA FOR "YES":
- Ethical approval obtained and documented
- Informed consent procedures described
- Confidentiality and anonymity protected
- Potential risks to participants considered
- Ethical principles upheld throughout

CRITERIA FOR "NO":
- No mention of ethical approval
- Informed consent not obtained
- Confidentiality concerns
- Potential harm to participants not addressed
- Ethical issues ignored

CRITERIA FOR "CAN'T TELL":
- Ethical approval mentioned but not detailed
- Consent procedures unclear
- Limited information about ethics
- Ethics partially addressed

WHAT TO LOOK FOR:
- Ethics approval statement (IRB, REC, etc.)
- Informed consent procedures
- Discussion of confidentiality
- Consideration of participant risks/benefits

Your Answer for Q7:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about ethical considerations]

---

QUESTION 8: Was the data analysis sufficiently rigorous?

CRITERIA FOR "YES":
- Clear description of analysis process
- Appropriate analytical framework (thematic analysis, grounded theory, etc.)
- Evidence of systematic and thorough analysis
- Multiple coders or verification procedures used
- Themes/findings well-supported by data
- Quotes or examples provided to illustrate findings

CRITERIA FOR "NO":
- Analysis method not described
- Insufficient detail about analytical process
- No evidence of systematic analysis
- Findings not well-supported by data
- Analytical approach inappropriate for data type
- No verification or quality checks

CRITERIA FOR "CAN'T TELL":
- Analysis method mentioned but not detailed
- Some rigor evident but not thoroughly described
- Unclear how findings were derived
- Mixed quality in analytical approach

WHAT TO LOOK FOR:
- Methods describing analytical framework
- Description of coding, theme development, or analysis process
- Discussion of inter-rater reliability or verification
- Examples, quotes, or evidence supporting themes

Your Answer for Q8:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about data analysis rigor]

---

SECTION C: HOW VALUABLE IS THE RESEARCH?

QUESTION 9: Is there a clear statement of findings?

CRITERIA FOR "YES":
- Findings clearly presented and well-organized
- Results directly address research aims
- Themes or categories are distinct and coherent
- Evidence provided to support each finding
- Findings are explicit and unambiguous

CRITERIA FOR "NO":
- Findings unclear or poorly organized
- Results don't address research aims
- Themes are vague or overlapping
- Insufficient evidence for findings
- Conclusions not supported by data

CRITERIA FOR "CAN'T TELL":
- Findings partially clear
- Some results well-presented, others unclear
- Mixed quality in findings presentation
- Incomplete reporting of results

WHAT TO LOOK FOR:
- Results section with clear themes or findings
- Evidence supporting each finding
- Coherence and organization of results
- Direct connection to research aims

Your Answer for Q9:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about findings clarity]

---

QUESTION 10: How valuable is the research?

CRITERIA FOR "YES" (High Value):
- Study contributes new insights or knowledge
- Findings have practical implications
- Research addresses important gap
- Results inform practice, policy, or future research
- Theoretical or practical contribution is clear

CRITERIA FOR "NO" (Low Value):
- Study lacks novelty or contribution
- Findings are trivial or already well-known
- Limited implications for practice or theory
- Poor quality limits value of findings
- No clear contribution to field

CRITERIA FOR "CAN'T TELL":
- Value is unclear or mixed
- Some contributions but limited
- Implications not fully articulated
- Moderate value but not groundbreaking

WHAT TO LOOK FOR:
- Discussion of implications for practice/policy
- Contribution to existing knowledge
- Recommendations for future research
- Practical applications discussed

NOTE: This is a holistic judgment about overall contribution and usefulness.

Your Answer for Q10:
- Answer: [Yes/No/Can't Tell]
- Justification: [Cite specific evidence about research value]

================================================================================
SCORING AND OVERALL ASSESSMENT:
================================================================================

After answering all 10 questions:
1. Count the number of "Yes" responses
2. Assign overall quality rating:
   - High Quality: 8-10 "Yes" responses (>80%)
   - Moderate Quality: 5-7 "Yes" responses (50-80%)
   - Low Quality: 0-4 "Yes" responses (<50%)

3. Provide overall summary (2-3 sentences)

================================================================================
RESPONSE FORMAT:
================================================================================

Return your assessment as valid JSON only (no markdown, no code blocks):

{{
  "q1": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q2": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q3": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q4": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q5": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q6": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q7": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q8": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q9": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "q10": {{"answer": "Yes/No/Can't Tell", "justification": "..."}},
  "summary": {{
    "yes_count": [number],
    "no_count": [number],
    "cant_tell_count": [number],
    "quality_rating": "High/Moderate/Low",
    "overall_notes": "2-3 sentence summary"
  }}
}}

Respond with JSON only:"""
    
    return prompt


def get_checklist_info(checklist_type: str) -> Dict[str, Any]:
    """
    Get metadata about a CASP checklist.
    
    Args:
        checklist_type: Type of checklist ('casp_rct', 'casp_cohort', 'casp_qualitative')
        
    Returns:
        Dictionary with checklist information
    """
    info_map = {
        'casp_rct': {
            'name': 'CASP RCT Checklist',
            'full_name': 'CASP Randomized Controlled Trial Checklist',
            'num_questions': 11,
            'sections': ['Validity (Q1-3)', 'Results (Q4-7)', 'Applicability (Q8-11)'],
            'scoring': {
                'high': '9-11 Yes responses (>80%)',
                'moderate': '5-8 Yes responses (50-80%)',
                'low': '0-4 Yes responses (<50%)'
            },
            'description': 'For randomized controlled trials and experimental studies'
        },
        'casp_cohort': {
            'name': 'CASP Cohort Study Checklist',
            'full_name': 'CASP Cohort Study Checklist',
            'num_questions': 12,
            'sections': ['Validity (Q1-6)', 'Results (Q7-9)', 'Applicability (Q10-12)'],
            'scoring': {
                'high': '10-12 Yes responses (>80%)',
                'moderate': '6-9 Yes responses (50-80%)',
                'low': '0-5 Yes responses (<50%)'
            },
            'description': 'For observational cohort studies and longitudinal research'
        },
        'casp_qualitative': {
            'name': 'CASP Qualitative Research Checklist',
            'full_name': 'CASP Qualitative Research Checklist',
            'num_questions': 10,
            'sections': ['Validity (Q1-6)', 'Results (Q7-8)', 'Value (Q9-10)'],
            'scoring': {
                'high': '8-10 Yes responses (>80%)',
                'moderate': '5-7 Yes responses (50-80%)',
                'low': '0-4 Yes responses (<50%)'
            },
            'description': 'For qualitative research including interviews, focus groups, and ethnography'
        }
    }
    
    return info_map.get(checklist_type, {})


def get_all_checklist_types() -> list:
    """Get list of all available CASP checklist types."""
    return ['casp_rct', 'casp_cohort', 'casp_qualitative']
