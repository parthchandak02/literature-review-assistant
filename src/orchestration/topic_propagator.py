"""
Topic Propagator System

Maintains and enriches topic context throughout the workflow,
ensuring topic awareness propagates through all agents.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TopicContext:
    """Maintains topic context and enriches it throughout workflow."""

    topic: str
    keywords: List[str] = field(default_factory=list)
    domain: Optional[str] = None
    scope: Optional[str] = None
    research_question: Optional[str] = None
    context: Optional[str] = None

    # Accumulated knowledge
    insights: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    extracted_data_summary: Optional[str] = None

    @classmethod
    def from_config(cls, config_dict: Dict[str, Any]) -> "TopicContext":
        """
        Initialize TopicContext from YAML configuration.

        Args:
            config_dict: Dictionary with topic configuration

        Returns:
            TopicContext instance
        """
        topic_config = config_dict.get("topic", {})

        # Handle simple string topic
        if isinstance(topic_config, str):
            return cls(topic=topic_config)

        # Handle structured topic config
        return cls(
            topic=topic_config.get("topic", ""),
            keywords=topic_config.get("keywords", []),
            domain=topic_config.get("domain"),
            scope=topic_config.get("scope"),
            research_question=topic_config.get("research_question"),
            context=topic_config.get("context"),
        )

    def enrich(self, insights: List[str]) -> None:
        """
        Add domain knowledge and insights as workflow progresses.

        Args:
            insights: List of insights to add
        """
        self.insights.extend(insights)

    def accumulate_findings(self, findings: List[Dict[str, Any]]) -> None:
        """
        Build knowledge base from extracted data.

        Args:
            findings: List of extracted findings/data
        """
        self.findings.extend(findings)

        # Create summary of findings
        if findings:
            summary_parts = []
            for i, finding in enumerate(findings[:10], 1):  # Top 10 findings
                if isinstance(finding, dict):
                    title = finding.get("title", f"Finding {i}")
                    key_findings = finding.get("key_findings", [])
                    if key_findings:
                        summary_parts.append(f"{title}: {', '.join(key_findings[:2])}")

            self.extracted_data_summary = "\n".join(summary_parts)

    def get_for_agent(self, agent_name: str) -> Dict[str, Any]:
        """
        Get topic context formatted for specific agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Dictionary with relevant context for the agent
        """
        base_context = {
            "topic": self.topic,
            "domain": self.domain or "general",
            "research_question": self.research_question or self.topic,
            "scope": self.scope,
            "keywords": self.keywords,
        }

        # Add accumulated insights for writing agents
        if "writer" in agent_name.lower():
            base_context["insights"] = self.insights[-10:]  # Last 10 insights
            base_context["findings_summary"] = self.extracted_data_summary

        # Add context for extraction agents
        if "extraction" in agent_name.lower():
            base_context["domain_context"] = self.context

        return base_context

    def inject_into_prompt(self, template: str) -> str:
        """
        Inject topic into prompt template.

        Args:
            template: Prompt template with placeholders

        Returns:
            Formatted prompt with topic injected
        """
        replacements = {
            "{topic}": self.topic,
            "{domain}": self.domain or "general",
            "{research_question}": self.research_question or self.topic,
            "{scope}": self.scope or "",
            "{keywords}": ", ".join(self.keywords) if self.keywords else "",
            "{context}": self.context or "",
        }

        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, str(value))

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "topic": self.topic,
            "keywords": self.keywords,
            "domain": self.domain,
            "scope": self.scope,
            "research_question": self.research_question,
            "context": self.context,
            "insights": self.insights,
            "findings_count": len(self.findings),
            "extracted_data_summary": self.extracted_data_summary,
        }

    def __str__(self) -> str:
        """String representation."""
        parts = [f"Topic: {self.topic}"]
        if self.domain:
            parts.append(f"Domain: {self.domain}")
        if self.research_question:
            parts.append(f"Research Question: {self.research_question}")
        if self.keywords:
            parts.append(f"Keywords: {', '.join(self.keywords)}")
        return "\n".join(parts)
