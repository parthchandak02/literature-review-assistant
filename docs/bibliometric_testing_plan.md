# Bibliometric Features Testing Plan

## Overview

This document outlines comprehensive testing for the newly implemented bibliometric features:
- Google Scholar Connector
- Enhanced Scopus Connector (with pybliometrics)
- Author Service
- Citation Network Builder
- Bibliometric Enricher
- Configuration and Integration

## Prerequisites

### Required Dependencies
```bash
pip install -e ".[bibliometrics]"
# or
pip install pybliometrics scholarly
```

### Required API Keys/Configuration
- **Scopus API Key**: `SCOPUS_API_KEY` (for enhanced Scopus features)
- **ScraperAPI Key**: `SCRAPERAPI_KEY` (recommended for Google Scholar to avoid CAPTCHAs)
- **Proxy Configuration**: Configure in `config/workflow.yaml` if using Google Scholar

### Test Data Requirements
- Known Scopus author IDs for testing
- Known Google Scholar author names
- Sample DOIs/EIDs for citation network testing
- Sample papers with bibliometric data

## Test Categories

### 1. Google Scholar Connector Tests

#### 1.1 Basic Search Functionality
**Test Case**: `test_google_scholar_basic_search`
- **Objective**: Verify basic publication search works
- **Steps**:
  1. Create GoogleScholarConnector instance
  2. Search for a known publication query
  3. Verify results are returned as Paper objects
- **Expected Results**:
  - Returns list of Paper objects
  - Papers have title, abstract, authors
  - Database field is "Google Scholar"
  - Citation counts populated if available
- **Test Query**: "machine learning" or "neural networks"

#### 1.2 Author Search
**Test Case**: `test_google_scholar_author_search`
- **Objective**: Verify author search functionality
- **Steps**:
  1. Search for a known author name
  2. Verify author profiles are returned
- **Expected Results**:
  - Returns list of author dictionaries
  - Author data includes name, ID, affiliation, h-index
- **Test Author**: "Geoffrey Hinton" or "Yann LeCun"

#### 1.3 Proxy Integration
**Test Case**: `test_google_scholar_proxy_setup`
- **Objective**: Verify proxy configuration works
- **Steps**:
  1. Configure proxy manager with ScraperAPI
  2. Create GoogleScholarConnector with proxy enabled
  3. Perform search
- **Expected Results**:
  - Proxy is configured successfully
  - No CAPTCHA errors
  - Search completes successfully
- **Configuration**: Set `SCRAPERAPI_KEY` environment variable

#### 1.4 Error Handling
**Test Case**: `test_google_scholar_error_handling`
- **Objective**: Verify graceful error handling
- **Steps**:
  1. Test without scholarly library installed
  2. Test with invalid queries
  3. Test with network errors
- **Expected Results**:
  - Appropriate error messages
  - No crashes
  - Graceful degradation

### 2. Enhanced Scopus Connector Tests

#### 2.1 Author Retrieval by ID
**Test Case**: `test_scopus_author_retrieval`
- **Objective**: Verify author profile retrieval using pybliometrics
- **Steps**:
  1. Get Scopus author ID (e.g., from search results)
  2. Call `get_author_by_id()` method
  3. Verify Author object is returned
- **Expected Results**:
  - Author object with name, ID, h-index, citation count
  - Current and historical affiliations populated
  - Subject areas included
  - Coauthor count available
- **Test Author ID**: Use a known Scopus author ID

#### 2.2 Affiliation Retrieval
**Test Case**: `test_scopus_affiliation_retrieval`
- **Objective**: Verify affiliation details retrieval
- **Steps**:
  1. Get Scopus affiliation ID
  2. Call `get_affiliation_by_id()` method
  3. Verify Affiliation object is returned
- **Expected Results**:
  - Affiliation object with name, city, country
  - Organization details populated
  - Author count available
- **Test Affiliation ID**: Use a known Scopus affiliation ID

#### 2.3 Author Search
**Test Case**: `test_scopus_author_search`
- **Objective**: Verify author search using Scopus query syntax
- **Steps**:
  1. Search using Scopus query syntax: `AUTHLAST(Smith) AND AUTHFIRST(John)`
  2. Verify Author objects are returned
- **Expected Results**:
  - List of Author objects matching query
  - Each author has complete profile data
- **Test Query**: `AUTHLAST(Hinton)` or similar

#### 2.4 Enhanced Search Results
**Test Case**: `test_scopus_enhanced_search`
- **Objective**: Verify search results include bibliometric fields
- **Steps**:
  1. Perform regular search
  2. Verify papers include new bibliometric fields
- **Expected Results**:
  - Papers have `citation_count` populated
  - Papers have `eid` (Scopus ID) populated
  - Papers have `subject_areas` populated
  - Papers have `scopus_id` populated
- **Test Query**: "machine learning"

#### 2.5 Fallback Without pybliometrics
**Test Case**: `test_scopus_without_pybliometrics`
- **Objective**: Verify connector works without pybliometrics
- **Steps**:
  1. Uninstall pybliometrics
  2. Perform regular search
  3. Try to call author retrieval methods
- **Expected Results**:
  - Regular search still works
  - Author retrieval returns None with warning
  - No crashes

### 3. Author Service Tests

#### 3.1 Unified Author Retrieval
**Test Case**: `test_author_service_get_author`
- **Objective**: Verify unified interface for author retrieval
- **Steps**:
  1. Create AuthorService with multiple connectors
  2. Retrieve author by ID from specific database
  3. Retrieve author by name (search)
- **Expected Results**:
  - Author retrieved successfully
  - Author object has bibliometric data
  - Works across different databases

#### 3.2 Author Profile Aggregation
**Test Case**: `test_author_service_aggregate_profiles`
- **Objective**: Verify aggregation from multiple sources
- **Steps**:
  1. Search for author in multiple databases
  2. Call `aggregate_author_profiles()`
  3. Verify aggregated profile
- **Expected Results**:
  - Profile combines data from multiple sources
  - Metrics are merged (max/average as appropriate)
  - Affiliations from all sources included
  - Subject areas combined

#### 3.3 Author Metrics Retrieval
**Test Case**: `test_author_service_get_metrics`
- **Objective**: Verify metrics extraction
- **Steps**:
  1. Get author by ID
  2. Call `get_author_metrics()`
  3. Verify metrics dictionary
- **Expected Results**:
  - Dictionary with h_index, citation_count, etc.
  - All metrics populated if available

#### 3.4 Coauthor Retrieval
**Test Case**: `test_author_service_get_coauthors`
- **Objective**: Verify coauthor network retrieval
- **Steps**:
  1. Get author profile
  2. Call `get_coauthors()`
  3. Verify coauthor list
- **Expected Results**:
  - List of Author objects (coauthors)
  - Coauthor relationships established

### 4. Citation Network Builder Tests

#### 4.1 Network Building from Papers
**Test Case**: `test_citation_network_build`
- **Objective**: Verify network construction from paper list
- **Steps**:
  1. Create CitationNetworkBuilder
  2. Add papers to network
  3. Call `build_network_from_papers()`
- **Expected Results**:
  - Network data structure created
  - Nodes represent papers
  - Edges represent citations
  - Statistics calculated

#### 4.2 Citation Edge Addition
**Test Case**: `test_citation_network_add_edge`
- **Objective**: Verify citation relationships are tracked
- **Steps**:
  1. Add citing paper and cited paper
  2. Call `add_citation()`
  3. Verify edge is created
- **Expected Results**:
  - Edge added to network
  - Both papers added as nodes
  - No duplicate edges

#### 4.3 Network Statistics
**Test Case**: `test_citation_network_statistics`
- **Objective**: Verify statistics calculation
- **Steps**:
  1. Build network with papers
  2. Call `get_citation_statistics()`
- **Expected Results**:
  - Total papers count
  - Total citations
  - Average citations
  - Max citations
  - Citation edges count

#### 4.4 NetworkX Export
**Test Case**: `test_citation_network_export`
- **Objective**: Verify NetworkX graph export
- **Steps**:
  1. Build network
  2. Call `export_networkx_graph()`
  3. Verify graph structure
- **Expected Results**:
  - NetworkX DiGraph object returned
  - Nodes have paper metadata
  - Edges have citation metadata
  - Can be used for visualization

#### 4.5 Paper ID Generation
**Test Case**: `test_citation_network_paper_ids`
- **Objective**: Verify unique ID generation for papers
- **Steps**:
  1. Add papers with different identifiers (DOI, EID, etc.)
  2. Verify unique IDs are generated
- **Expected Results**:
  - IDs are unique
  - IDs are deterministic (same paper = same ID)
  - Handles papers without DOI/EID

### 5. Bibliometric Enricher Tests

#### 5.1 Paper Enrichment
**Test Case**: `test_bibliometric_enricher_enrich`
- **Objective**: Verify papers are enriched with bibliometric data
- **Steps**:
  1. Create BibliometricEnricher with AuthorService
  2. Enrich list of papers
  3. Verify enriched papers
- **Expected Results**:
  - Papers have author metrics if available
  - Citation counts preserved
  - Subject areas included

#### 5.2 Author Metrics Enrichment
**Test Case**: `test_bibliometric_enricher_author_metrics`
- **Objective**: Verify author metrics are added to papers
- **Steps**:
  1. Enrich papers with author names
  2. Verify h-index and citation counts added
- **Expected Results**:
  - Papers have h_index if author found
  - Author-level citation counts added

#### 5.3 Citation Network Building
**Test Case**: `test_bibliometric_enricher_network`
- **Objective**: Verify citation network is built
- **Steps**:
  1. Create enricher with CitationNetworkBuilder
  2. Build network from papers
- **Expected Results**:
  - Network data structure created
  - Statistics available

### 6. Configuration Tests

#### 6.1 Bibliometrics Configuration
**Test Case**: `test_bibliometrics_config`
- **Objective**: Verify configuration is read correctly
- **Steps**:
  1. Load workflow.yaml with bibliometrics config
  2. Verify settings are parsed
- **Expected Results**:
  - `bibliometrics.enabled` read correctly
  - Feature flags (include_author_metrics, etc.) read correctly
  - Google Scholar settings read correctly

#### 6.2 Google Scholar Configuration
**Test Case**: `test_google_scholar_config`
- **Objective**: Verify Google Scholar connector respects config
- **Steps**:
  1. Configure Google Scholar in workflow.yaml
  2. Create connector via factory
  3. Verify proxy settings applied
- **Expected Results**:
  - Connector created with correct proxy settings
  - Use_proxy flag respected

### 7. Integration Tests

#### 7.1 Workflow Integration
**Test Case**: `test_workflow_with_bibliometrics`
- **Objective**: Verify bibliometric features work in full workflow
- **Steps**:
  1. Run workflow with bibliometrics enabled
  2. Verify papers have bibliometric data
  3. Verify author service is available
- **Expected Results**:
  - Workflow completes successfully
  - Papers enriched with bibliometric data
  - No errors related to bibliometrics

#### 7.2 Database Connector Factory Integration
**Test Case**: `test_factory_google_scholar`
- **Objective**: Verify Google Scholar connector created via factory
- **Steps**:
  1. Add "Google Scholar" to databases list
  2. Create connectors via factory
  3. Verify Google Scholar connector created
- **Expected Results**:
  - Google Scholar connector created successfully
  - Proxy configured if available
  - Graceful handling if scholarly not installed

#### 7.3 Multi-Database Author Retrieval
**Test Case**: `test_multi_database_author_search`
- **Objective**: Verify author search across multiple databases
- **Steps**:
  1. Create AuthorService with Scopus and Google Scholar
  2. Search for author
  3. Verify results from both databases
- **Expected Results**:
  - Results from both databases
  - Profiles can be aggregated

### 8. Edge Cases and Error Handling

#### 8.1 Missing Dependencies
**Test Case**: `test_missing_dependencies`
- **Objective**: Verify graceful degradation without optional dependencies
- **Steps**:
  1. Test without pybliometrics
  2. Test without scholarly
  3. Verify appropriate warnings/errors
- **Expected Results**:
  - Clear error messages
  - No crashes
  - Core functionality still works

#### 8.2 Invalid API Keys
**Test Case**: `test_invalid_api_keys`
- **Objective**: Verify handling of invalid credentials
- **Steps**:
  1. Use invalid Scopus API key
  2. Use invalid ScraperAPI key
  3. Verify error handling
- **Expected Results**:
  - Appropriate error messages
  - No crashes
  - Connectors handle errors gracefully

#### 8.3 Network Failures
**Test Case**: `test_network_failures`
- **Objective**: Verify handling of network issues
- **Steps**:
  1. Simulate network failures
  2. Verify retry logic
  3. Verify error handling
- **Expected Results**:
  - Retries attempted
  - Appropriate error messages
  - No crashes

#### 8.4 Empty Results
**Test Case**: `test_empty_results`
- **Objective**: Verify handling of empty search results
- **Steps**:
  1. Search with query that returns no results
  2. Verify empty list returned
- **Expected Results**:
  - Empty list returned (not None)
  - No errors

### 9. Performance Tests

#### 9.1 Author Retrieval Performance
**Test Case**: `test_author_retrieval_performance`
- **Objective**: Verify author retrieval is reasonably fast
- **Steps**:
  1. Measure time to retrieve author profile
  2. Measure time for author search
- **Expected Results**:
  - Author retrieval < 5 seconds
  - Author search < 10 seconds

#### 9.2 Citation Network Performance
**Test Case**: `test_citation_network_performance`
- **Objective**: Verify network building is efficient
- **Steps**:
  1. Build network with 100 papers
  2. Measure time
- **Expected Results**:
  - Network building < 30 seconds for 100 papers

### 10. Data Validation Tests

#### 10.1 Author Data Validation
**Test Case**: `test_author_data_validation`
- **Objective**: Verify Author objects have valid data
- **Steps**:
  1. Retrieve author
  2. Validate all fields
- **Expected Results**:
  - Required fields present
  - Data types correct
  - No None values for required fields

#### 10.2 Paper Bibliometric Fields Validation
**Test Case**: `test_paper_bibliometric_validation`
- **Objective**: Verify bibliometric fields are valid
- **Steps**:
  1. Search papers
  2. Validate bibliometric fields
- **Expected Results**:
  - Citation counts are integers >= 0
  - Subject areas are lists of strings
  - EIDs are valid Scopus format

## Test Execution Strategy

### Phase 1: Unit Tests (Isolated Components)
1. Run unit tests for each component individually
2. Mock external dependencies (API calls)
3. Verify component behavior in isolation

### Phase 2: Integration Tests (Component Interaction)
1. Test components working together
2. Use real API keys for external services
3. Verify data flow between components

### Phase 3: End-to-End Tests (Full Workflow)
1. Run complete workflow with bibliometrics enabled
2. Verify all features work together
3. Check output quality

### Phase 4: Performance and Stress Tests
1. Test with large datasets
2. Measure performance metrics
3. Identify bottlenecks

## Test Data

### Sample Test Data
- **Scopus Author IDs**: 
  - Example: "7004212771" (Geoffrey Hinton)
  - Example: "7004212771" (Yann LeCun)
  
- **Google Scholar Author Names**:
  - "Geoffrey Hinton"
  - "Yann LeCun"
  - "Andrew Ng"

- **Test Papers**:
  - Papers with known citation counts
  - Papers with DOIs
  - Papers with Scopus EIDs

- **Test Queries**:
  - "machine learning"
  - "neural networks"
  - "deep learning"

## Success Criteria

### Functional Requirements
- [ ] All connectors can be instantiated
- [ ] Author retrieval works for both Scopus and Google Scholar
- [ ] Citation networks can be built
- [ ] Papers are enriched with bibliometric data
- [ ] Configuration is respected

### Non-Functional Requirements
- [ ] Error handling is graceful
- [ ] Performance is acceptable (< 5s for single operations)
- [ ] Code handles missing dependencies
- [ ] Documentation is accurate

### Integration Requirements
- [ ] Works with existing workflow
- [ ] Doesn't break existing functionality
- [ ] Optional features degrade gracefully

## Test Scripts

### Quick Test Script
```python
# tests/integration/test_bibliometric_features_quick.py
"""
Quick smoke test for bibliometric features.
"""
import pytest
from src.search.connectors.google_scholar_connector import GoogleScholarConnector
from src.search.database_connectors import ScopusConnector
from src.search.author_service import AuthorService
from src.search.citation_network import CitationNetworkBuilder

def test_quick_smoke():
    """Quick smoke test of all bibliometric features."""
    # Test Google Scholar connector creation
    try:
        gs = GoogleScholarConnector(use_proxy=False)
        assert gs.get_database_name() == "Google Scholar"
    except ImportError:
        pytest.skip("scholarly not installed")
    
    # Test Scopus enhanced features
    scopus = ScopusConnector(api_key="test_key")
    assert hasattr(scopus, 'get_author_by_id')
    assert hasattr(scopus, 'get_affiliation_by_id')
    assert hasattr(scopus, 'search_authors')
    
    # Test Author Service
    connectors = {}
    if scopus.api_key:
        connectors["Scopus"] = scopus
    author_service = AuthorService(connectors)
    assert author_service is not None
    
    # Test Citation Network Builder
    network_builder = CitationNetworkBuilder()
    assert network_builder is not None
    
    print("All bibliometric components can be instantiated!")
```

### Comprehensive Test Suite
See individual test files:
- `tests/unit/search/test_google_scholar_connector.py`
- `tests/unit/search/test_author_service.py`
- `tests/unit/search/test_citation_network.py`
- `tests/integration/test_bibliometric_integration.py` (to be created)

## Running Tests

### Run All Bibliometric Tests
```bash
pytest tests/unit/search/test_google_scholar_connector.py \
       tests/unit/search/test_author_service.py \
       tests/unit/search/test_citation_network.py \
       -v
```

### Run Integration Tests
```bash
pytest tests/integration/test_bibliometric_integration.py -v
```

### Run with Coverage
```bash
pytest tests/unit/search/test_*bibliometric*.py \
       --cov=src/search \
       --cov-report=html
```

## Notes

- Some tests require API keys - use environment variables or test fixtures
- Google Scholar tests may be flaky due to CAPTCHAs - use proxies
- Scopus tests require valid API key - use test account if available
- Mock external API calls in unit tests for reliability
- Use real API calls only in integration tests
