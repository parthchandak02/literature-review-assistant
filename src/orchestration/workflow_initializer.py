"""
Workflow Initializer

Handles initialization of all workflow components.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from ..config.config_loader import ConfigLoader
from ..config.debug_config import get_debug_config_from_env, load_debug_config
from ..observability.cost_tracker import get_cost_tracker
from ..observability.metrics import get_metrics_collector
from ..orchestration.handoff_protocol import HandoffProtocol
from ..orchestration.topic_propagator import TopicContext
from ..utils.logging_config import LogLevel, setup_logging

try:
    from ..observability.tracing import TracingContext, set_tracing_context
except ImportError:
    TracingContext = None

    def set_tracing_context(x):
        return None


from src.deduplication import Deduplicator
from src.extraction.data_extractor_agent import DataExtractorAgent
from src.screening.fulltext_agent import FullTextScreener
from src.screening.title_abstract_agent import TitleAbstractScreener
from src.search.multi_database_searcher import MultiDatabaseSearcher
from src.utils.pdf_retriever import PDFRetriever


class WorkflowInitializer:
    """Handles initialization of workflow components."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize workflow components.

        Args:
            config_path: Path to YAML config file
        """
        # Load unified YAML configuration
        loader = ConfigLoader(config_path)
        raw_config = loader.load()
        raw_config = loader.substitute_env_vars(raw_config)
        loader.validate(raw_config)

        # Initialize topic context
        self.topic_context = TopicContext.from_config(raw_config)

        # Apply template replacement to config
        self.config = loader.apply_template_replacement(raw_config, self.topic_context)

        # Extract workflow settings
        workflow_config = self.config["workflow"]
        output_config = self.config["output"]

        # Initialize PRISMA counter stub (for tracking counts only, no diagram generation)
        from .prisma_counter_stub import PRISMACounter
        self.prisma_counter = PRISMACounter()
        
        self.output_dir = Path(output_config["directory"])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Get LLM settings
        llm_provider = os.getenv("LLM_PROVIDER", "gemini")

        # Detect API key based on provider
        llm_api_key = None
        if llm_provider == "gemini":
            llm_api_key = os.getenv("GEMINI_API_KEY")
        elif llm_provider == "perplexity":
            llm_api_key = os.getenv("PERPLEXITY_API_KEY")

        # Get agent configurations from YAML
        agents_config = self.config.get("agents", {})

        # Get topic context for agents
        agent_topic_context = self.topic_context.get_for_agent("all")

        # Initialize components
        self.search_strategy = None
        self.searcher = MultiDatabaseSearcher()
        self.deduplicator = Deduplicator(
            similarity_threshold=workflow_config.get("similarity_threshold", 85)
        )

        # Initialize agents with YAML configs and topic context
        # Use separate configs for screening stages
        title_abstract_config = agents_config.get("title_abstract_screener", {})
        fulltext_config = agents_config.get("fulltext_screener", {})
        extraction_config = agents_config.get("extraction_agent", {})

        self.title_screener = TitleAbstractScreener(
            llm_provider, llm_api_key, agent_topic_context, title_abstract_config
        )
        self.fulltext_screener = FullTextScreener(
            llm_provider, llm_api_key, agent_topic_context, fulltext_config
        )
        self.extractor = DataExtractorAgent(
            llm_provider, llm_api_key, agent_topic_context, extraction_config
        )

        # Handoff protocol
        self.handoff_protocol = HandoffProtocol()

        # Debug configuration
        self.debug_config = load_debug_config(config_path) or get_debug_config_from_env()

        # Observability
        self.metrics = get_metrics_collector()
        self.cost_tracker = get_cost_tracker()
        self.tracing_context = (
            TracingContext() if (self.debug_config.show_traces and TracingContext) else None
        )
        if self.tracing_context:
            set_tracing_context(self.tracing_context)

        # Initialize logging if debug enabled
        if self.debug_config.enabled:
            setup_logging(
                level=LogLevel(self.debug_config.level.value),
                log_to_file=self.debug_config.log_to_file,
                log_file=self.debug_config.log_file,
                verbose=self.debug_config.level in [LogLevel.DETAILED, LogLevel.FULL],
                debug=self.debug_config.level == LogLevel.FULL,
            )

