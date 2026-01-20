# Execution Flow Analysis

## End-to-End Execution Path

### Entry Point: `main.py`

```
main.py::main()
  -> parse_args()  # Parse command line arguments
  -> WorkflowManager(config_path)  # Initialize workflow manager
  -> WorkflowManager.run()  # Execute workflow
```

### Workflow Execution: `WorkflowManager.run()`

#### Phase 1: Build Search Strategy
```
WorkflowManager.run()
  -> _build_search_strategy()
    -> SearchStrategyBuilder.build_strategy()
      -> Generates search queries for each database
  -> Checkpoint: "build_search_strategy" (if enabled)
```

#### Phase 2: Search Databases
```
  -> _search_databases()
    -> MultiDatabaseSearcher.search_all_databases()
      -> For each database:
        -> DatabaseConnector.search()
          -> PubMedConnector / ArxivConnector / SemanticScholarConnector / etc.
      -> Returns: List[Paper]
  -> self.all_papers = results
  -> PRISMA: set_found(count, database_breakdown)
  -> Checkpoint: "search_databases"
```

#### Phase 3: Deduplication
```
  -> deduplicator.deduplicate_papers(self.all_papers)
    -> FuzzyWuzzyDeduplicator.deduplicate()
      -> Compares papers using fuzzy matching
      -> Returns: List[Paper] (unique)
  -> self.unique_papers = results
  -> PRISMA: set_no_dupes(count)
  -> Checkpoint: "deduplication"
```

#### Phase 4: Title/Abstract Screening
```
  -> _screen_title_abstract()
    -> TitleAbstractScreener.screen() for each paper
      -> BaseScreeningAgent.screen()
        -> LLM call with inclusion/exclusion criteria
        -> Returns: ScreeningResult
    -> self.screened_papers = included papers
    -> PRISMA: set_screened(count), set_screen_exclusions(count)
  -> Checkpoint: "title_abstract_screening"
```

#### Phase 5: Full-text Screening
```
  -> _screen_fulltext()
    -> For each screened paper:
      -> pdf_retriever.retrieve_full_text(paper)
        -> Attempts to retrieve PDF
        -> Tracks: fulltext_available_count, fulltext_unavailable_count
      -> FullTextScreener.screen()
        -> LLM call with full-text content
        -> Returns: ScreeningResult
    -> self.eligible_papers = included papers
    -> PRISMA: 
      -> set_full_text_sought(len(screened_papers))
      -> set_full_text_not_retrieved(fulltext_unavailable_count)
      -> set_full_text_assessed(len(screened_papers))  # All papers assessed
      -> set_full_text_exclusions(excluded_count)
  -> Checkpoint: "fulltext_screening"
```

#### Phase 6: Final Inclusion
```
  -> self.final_papers = self.eligible_papers
  -> PRISMA: set_qualitative(count), set_quantitative(count)
```

#### Phase 6.5: Paper Enrichment
```
  -> _enrich_papers()
    -> PaperEnricher.enrich_papers(self.final_papers)
      -> Enriches with missing metadata (affiliations, countries, etc.)
  -> Checkpoint: "paper_enrichment"
```

#### Phase 7: Data Extraction
```
  -> _extract_data()
    -> DataExtractorAgent.extract() for each paper
      -> LLM call with extraction schema
      -> Returns: ExtractedData
    -> self.extracted_data = results
  -> Checkpoint: "data_extraction"
```

#### Phase 8: Quality Assessment
```
  -> _assess_quality()
    -> RiskOfBiasAssessor.assess() for each paper
      -> RoB 2 or ROBINS-I assessment
    -> GradeAssessor.assess() for outcomes
      -> GRADE assessment
    -> Generates quality assessment templates
  -> Checkpoint: "quality_assessment"
```

#### Phase 9: PRISMA Diagram Generation
```
  -> _generate_prisma_diagram()
    -> PRISMAGenerator.generate()
      -> Validates PRISMA counts
      -> Generates diagram using prisma-flow-diagram library
      -> Saves: prisma_diagram.png
```

#### Phase 10: Visualization Generation
```
  -> _generate_visualizations()
    -> ChartsGenerator.generate_all()
      -> generate_publication_timeline()
      -> generate_network_graph()
      -> generate_geographic_distribution()
      -> generate_subject_distribution()
    -> Saves: *.png, network_graph.html
```

#### Phase 11: Article Writing
```
  -> _write_article()
    -> IntroductionWriter.write()
      -> LLM call to generate introduction
    -> MethodsWriter.write()
      -> LLM call to generate methods
    -> ResultsWriter.write()
      -> LLM call to generate results
    -> DiscussionWriter.write()
      -> LLM call to generate discussion
    -> AbstractGenerator.generate()
      -> LLM call to generate PRISMA 2020 abstract
    -> self._article_sections = {intro, methods, results, discussion, abstract}
  -> Checkpoint: "article_writing"
```

#### Phase 12: Final Report Compilation
```
  -> _generate_final_report()
    -> Assembles all sections
    -> Processes citations
    -> Generates:
      -> final_report.md
      -> prisma_checklist.json
      -> search_strategies.md
      -> data_extraction_form.md
      -> references.bib (if BibTeX enabled)
```

## Data Flow Between Phases

```
all_papers (Phase 2)
  -> unique_papers (Phase 3)
    -> screened_papers (Phase 4)
      -> eligible_papers (Phase 5)
        -> final_papers (Phase 6)
          -> enriched final_papers (Phase 6.5)
            -> extracted_data (Phase 7)
              -> quality_assessments (Phase 8)
                -> article_sections (Phase 11)
                  -> final_report (Phase 12)
```

## PRISMA Count Flow

```
found (Phase 2)
  -> no_dupes (Phase 3)
    -> screened (Phase 4)
      -> full_text_sought (Phase 5)
        -> full_text_not_retrieved (Phase 5)
        -> full_text_assessed (Phase 5)
          -> full_text_exclusions (Phase 5)
            -> qualitative/quantitative (Phase 6)
```

## Checkpoint Resumption Flow

```
main.py
  -> WorkflowManager(config_path)
    -> _find_existing_checkpoint_by_topic()
      -> Finds checkpoint directory matching topic
      -> Loads latest phase
    -> Loads all prerequisite checkpoints:
      -> _load_phase_state() for each dependency
        -> Deserializes papers, results, counts
        -> Restores PRISMA counts
        -> Accumulates state
    -> Resumes from latest phase
      -> Continues workflow from checkpoint
```

## Validation Points

1. **Phase Dependencies**: All phases have correct dependencies defined
2. **Data Flow**: Each phase receives correct input data
3. **PRISMA Counts**: Counts are tracked and validated at each phase
4. **Checkpoint System**: Checkpoints save and load correctly
5. **Output Generation**: All outputs are generated correctly

## Issues Found and Fixed

1. ✅ **PRISMA Count Calculation**: Fixed `assessed` count to properly track all assessed papers
2. ✅ **Validation Logic**: Improved validation to catch count mismatches earlier
3. ✅ **Missing Checkpoint**: `paper_enrichment` checkpoint handling improved
4. ✅ **Import Error**: Verified `get_llm_tool` import error is resolved

## Execution Validation

The end-to-end flow has been validated:
- ✅ All 12 phases execute in correct order
- ✅ Data flows correctly between phases
- ✅ Checkpoints save and load correctly
- ✅ PRISMA counts are tracked throughout
- ✅ All outputs are generated correctly
- ✅ No circular dependencies found
- ✅ All critical imports resolve correctly
