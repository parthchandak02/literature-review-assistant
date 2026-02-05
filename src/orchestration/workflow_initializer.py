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
from ..config.debug_config import load_debug_config, get_debug_config_from_env
from ..utils.logging_config import setup_logging, LogLevel
from ..observability.metrics import get_metrics_collector
from ..observability.cost_tracker import get_cost_tracker
from ..orchestration.topic_propagator import TopicContext
from ..orchestration.handoff_protocol import HandoffProtocol

try:
    from ..observability.tracing import TracingContext, set_tracing_context
except ImportError:
    TracingContext = None

    def set_tracing_context(x):
        return None

from src.prisma.prisma_generator import PRISMACounter
from src.search.multi_database_searcher import MultiDatabaseSearcher
from src.deduplication import Deduplicator
from src.screening.title_abstract_agent import TitleAbstractScreener
from src.screening.fulltext_agent import FullTextScreener
from src.extraction.data_extractor_agent import DataExtractorAgent
from src.visualization.charts import ChartGenerator
from src.writing.introduction_agent import IntroductionWriter
from src.writing.methods_agent import MethodsWriter
from src.writing.results_agent import ResultsWriter
from src.writing.discussion_agent import DiscussionWriter
from src.writing.abstract_agent import AbstractGenerator
from src.writing.style_pattern_extractor import StylePatternExtractor
from src.writing.humanization_agent import HumanizationAgent
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

        # Initialize PRISMA counter
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
        # Use separate configs for screening stages, with fallback to screening_agent for backward compatibility
        title_abstract_config = agents_config.get("title_abstract_screener") or agents_config.get("screening_agent", {})
        fulltext_config = agents_config.get("fulltext_screener") or agents_config.get("screening_agent", {})
        extraction_config = agents_config.get("extraction_agent", {})
        intro_config = agents_config.get("introduction_writer", {})
        methods_config = agents_config.get("methods_writer", {})
        results_config = agents_config.get("results_writer", {})
        discussion_config = agents_config.get("discussion_writer", {})

        self.title_screener = TitleAbstractScreener(
            llm_provider, llm_api_key, agent_topic_context, title_abstract_config
        )
        self.fulltext_screener = FullTextScreener(
            llm_provider, llm_api_key, agent_topic_context, fulltext_config
        )
        self.extractor = DataExtractorAgent(
            llm_provider, llm_api_key, agent_topic_context, extraction_config
        )
        self.chart_generator = ChartGenerator(str(self.output_dir))
        self.intro_writer = IntroductionWriter(
            llm_provider, llm_api_key, agent_topic_context, intro_config
        )
        self.methods_writer = MethodsWriter(
            llm_provider, llm_api_key, agent_topic_context, methods_config
        )
        self.results_writer = ResultsWriter(
            llm_provider, llm_api_key, agent_topic_context, results_config
        )
        self.discussion_writer = DiscussionWriter(
            llm_provider, llm_api_key, agent_topic_context, discussion_config
        )
        
        # Register tools for writing agents
        self._register_writing_tools()
        
        # Abstract generator
        abstract_config = agents_config.get("abstract_generator", {})
        # Pass full config so abstract generator can access topic.protocol and topic.funding
        self.abstract_generator = AbstractGenerator(
            llm_provider, llm_api_key, agent_topic_context, self.config
        )

        # Style pattern extractor and humanization agent
        writing_config = self.config.get("writing", {})
        style_extraction_config = writing_config.get("style_extraction", {})
        humanization_config = writing_config.get("humanization", {})
        
        # Initialize PDF retriever for style extraction (reuses cached full-text)
        pdf_cache_dir = str(self.output_dir / "pdf_cache")
        pdf_retriever = PDFRetriever(cache_dir=pdf_cache_dir)
        
        # Style pattern extractor
        if style_extraction_config.get("enabled", True):
            self.style_pattern_extractor = StylePatternExtractor(
                llm_provider=llm_provider,
                api_key=llm_api_key,
                agent_config=style_extraction_config,
                pdf_retriever=pdf_retriever,
            )
        else:
            self.style_pattern_extractor = None
        
        # Humanization agent
        if humanization_config.get("enabled", True):
            self.humanization_agent = HumanizationAgent(
                llm_provider=llm_provider,
                api_key=llm_api_key,
                agent_config=humanization_config,
            )
        else:
            self.humanization_agent = None

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
    
    def _register_writing_tools(self):
        """Register tools for writing agents."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from ..tools.mermaid_diagram_tool import create_mermaid_diagram_tool, MERMAID_AVAILABLE
            from ..tools.table_generator_tool import create_table_generator_tools, TABULATE_AVAILABLE
            
            if not MERMAID_AVAILABLE:
                logger.warning("mermaid-py not installed. Mermaid diagram tool will not be available.")
            if not TABULATE_AVAILABLE:
                logger.warning("tabulate not installed. Table generation tools will not be available.")
            
            if not MERMAID_AVAILABLE and not TABULATE_AVAILABLE:
                logger.warning("Neither mermaid-py nor tabulate are installed. Tool calling will be disabled.")
                return
            
            output_dir = str(self.output_dir)
            
            # Register Mermaid diagram tool if available
            if MERMAID_AVAILABLE:
                try:
                    mermaid_tool = create_mermaid_diagram_tool(output_dir)
                    self.results_writer.register_tool(mermaid_tool)
                    self.methods_writer.register_tool(mermaid_tool)
                    logger.info("Registered Mermaid diagram tool for writing agents")
                except Exception as e:
                    logger.warning(f"Failed to register Mermaid diagram tool: {e}")
            
            # Register table generation tools if available
            if TABULATE_AVAILABLE:
                try:
                    table_tools = create_table_generator_tools(output_dir)
                    for tool in table_tools:
                        self.results_writer.register_tool(tool)
                        self.methods_writer.register_tool(tool)
                    logger.info(f"Registered {len(table_tools)} table generation tools for writing agents")
                except Exception as e:
                    logger.warning(f"Failed to register table generation tools: {e}")
            
        except ImportError as e:
            # Tools are optional - log warning but don't fail
            logger.warning(f"Could not import writing tools: {e}. Tool calling will be disabled.")
        except Exception as e:
            logger.warning(f"Error registering writing tools: {e}. Tool calling may be disabled.", exc_info=True)
