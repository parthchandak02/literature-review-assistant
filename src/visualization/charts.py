"""
Bibliometric Charts Generator

Generates charts for papers per year, countries, subject areas, etc.
"""

import matplotlib.pyplot as plt
import pandas as pd
import re
import logging
from typing import List, Optional, Dict, Set, Any
from pathlib import Path
from collections import Counter
from ..search.database_connectors import Paper

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import pycountry
    PYCOUNTRY_AVAILABLE = True
except ImportError:
    PYCOUNTRY_AVAILABLE = False


class ChartGenerator:
    """Generates bibliometric charts."""

    def __init__(self, output_dir: str = "data/outputs"):
        """
        Initialize chart generator.

        Args:
            output_dir: Directory to save charts
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def papers_per_year(self, papers: List[Paper], output_path: Optional[str] = None) -> str:
        """
        Generate chart showing number of papers published per year.

        Args:
            papers: List of Paper objects
            output_path: Optional output path (default: auto-generated)

        Returns:
            Path to saved chart
        """
        if not papers:
            return ""

        # Extract years
        years = [p.year for p in papers if p.year]

        if not years:
            return ""

        # Count papers per year
        year_counts = pd.Series(years).value_counts().sort_index()

        # Create chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(year_counts.index, year_counts.values, color="steelblue", alpha=0.7)
        ax.set_xlabel("Year", fontsize=12)
        ax.set_ylabel("Number of Papers", fontsize=12)
        ax.set_title("Number of Papers Published Per Year", fontsize=14, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)

        # Rotate x-axis labels if needed
        if len(year_counts) > 10:
            plt.xticks(rotation=45, ha="right")

        plt.tight_layout()

        # Save
        if not output_path:
            output_path = self.output_dir / "papers_per_year.png"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)

    def papers_by_country(
        self, papers: List[Paper], output_path: Optional[str] = None, top_n: int = 10
    ) -> str:
        """
        Generate chart showing papers by country/territory.

        Args:
            papers: List of Paper objects
            output_path: Optional output path
            top_n: Number of top countries to show

        Returns:
            Path to saved chart
        """
        if not papers:
            return ""

        # Extract countries from papers
        countries = []
        for paper in papers:
            # Try multiple methods to get country
            country = None
            
            # Method 1: Direct country field
            if paper.country:
                country = paper.country
            # Method 2: Extract from affiliations (now that we're extracting them!)
            elif paper.affiliations:
                country = self._extract_country_from_affiliations(paper.affiliations)
            # Method 3: Infer from journal/database
            elif paper.journal:
                country = self._infer_country_from_journal(paper.journal)
            
            # Normalize country name using pycountry if available
            if country and PYCOUNTRY_AVAILABLE:
                try:
                    # Try to find and normalize the country name
                    normalized = None
                    # Try exact match first
                    try:
                        c = pycountry.countries.get(name=country)
                        if c:
                            normalized = c.name
                    except (KeyError, AttributeError):
                        pass
                    
                    # Try common name
                    if not normalized:
                        for c in pycountry.countries:
                            if hasattr(c, 'common_name') and c.common_name and c.common_name == country:
                                normalized = c.name
                                break
                    
                    if normalized:
                        country = normalized
                except Exception:
                    # If normalization fails, use original
                    pass
            
            if country:
                countries.append(country)

        if not countries:
            # Fallback: Create placeholder chart
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(
                0.5,
                0.5,
                "Country data not available\n(requires affiliation parsing)",
                ha="center",
                va="center",
                fontsize=12,
            )
            ax.set_title("Documents by Country/Territory", fontsize=14, fontweight="bold")
            ax.axis("off")

            if not output_path:
                output_path = self.output_dir / "papers_by_country.png"
            else:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            plt.close()
            return str(output_path)

        # Count countries
        country_counts = Counter(countries)
        top_countries = country_counts.most_common(top_n)

        if not top_countries:
            return ""

        # Create chart
        countries_list, counts_list = zip(*top_countries)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        bars = ax.barh(range(len(countries_list)), counts_list, color="steelblue", alpha=0.7)
        ax.set_yticks(range(len(countries_list)))
        ax.set_yticklabels(countries_list)
        ax.set_xlabel("Number of Papers", fontsize=12)
        ax.set_ylabel("Country", fontsize=12)
        ax.set_title("Documents by Country/Territory", fontsize=14, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)

        # Add value labels on bars
        for i, (country, count) in enumerate(top_countries):
            ax.text(count + 0.1, i, str(count), va="center", fontsize=10)

        plt.tight_layout()

        if not output_path:
            output_path = self.output_dir / "papers_by_country.png"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)

    def _extract_country_from_affiliations(self, affiliations: List[str]) -> Optional[str]:
        """Extract country from affiliation strings using pycountry and pattern matching."""
        if not affiliations:
            return None
        
        # Common country patterns and abbreviations
        country_patterns = {
            r"\bUSA\b": "United States",
            r"\bU\.S\.A\.\b": "United States",
            r"\bUS\b": "United States",
            r"\bUnited States\b": "United States",
            r"\bUK\b": "United Kingdom",
            r"\bU\.K\.\b": "United Kingdom",
            r"\bUnited Kingdom\b": "United Kingdom",
            r"\bGB\b": "United Kingdom",
            r"\bGreat Britain\b": "United Kingdom",
            r"\bSouth Korea\b": "South Korea",
            r"\bKorea\b": "South Korea",  # Default to South Korea if ambiguous
            r"\bRepublic of Korea\b": "South Korea",
        }
        
        # Build a set of all country names and common names from pycountry
        country_names = set()
        country_common_names = {}
        if PYCOUNTRY_AVAILABLE:
            for country in pycountry.countries:
                country_names.add(country.name.upper())
                if hasattr(country, 'common_name') and country.common_name:
                    country_names.add(country.common_name.upper())
                    country_common_names[country.common_name.upper()] = country.name
                # Also add alpha_2 and alpha_3 codes
                country_names.add(country.alpha_2.upper())
                country_names.add(country.alpha_3.upper())
        
        # Search through affiliations (typically country is at the end)
        for affiliation in affiliations:
            if not affiliation:
                continue
                
            affiliation_upper = affiliation.upper()
            
            # First try pattern matching for common abbreviations
            for pattern, country in country_patterns.items():
                if re.search(pattern, affiliation_upper, re.IGNORECASE):
                    return country
            
            # Try to find country name using pycountry
            if PYCOUNTRY_AVAILABLE:
                # Split affiliation by common delimiters and check each part
                parts = re.split(r'[,;]|\s+', affiliation_upper)
                # Check from end (country usually at the end)
                for part in reversed(parts):
                    part = part.strip()
                    if not part or len(part) < 2:
                        continue
                    
                    # Check if it's a country code
                    if len(part) == 2 or len(part) == 3:
                        try:
                            country = pycountry.countries.get(alpha_2=part) or pycountry.countries.get(alpha_3=part)
                            if country:
                                return country.name
                        except (KeyError, AttributeError):
                            pass
                    
                    # Check if it matches a country name
                    if part in country_names:
                        if part in country_common_names:
                            return country_common_names[part]
                        # Find the country object
                        try:
                            for country in pycountry.countries:
                                if country.name.upper() == part:
                                    return country.name
                                if hasattr(country, 'common_name') and country.common_name and country.common_name.upper() == part:
                                    return country.name
                        except (KeyError, AttributeError):
                            pass
                    
                    # Try fuzzy matching - check if part contains a country name
                    for country_name in country_names:
                        if len(country_name) > 3 and country_name in part:
                            try:
                                country = pycountry.countries.get(name=country_name)
                                if country:
                                    return country.name
                            except (KeyError, AttributeError):
                                pass
        
        return None

    def _infer_country_from_journal(self, journal: str) -> Optional[str]:
        """Infer country from journal name (limited accuracy)."""
        journal_lower = journal.lower()
        
        # Some journals have country indicators
        if "american" in journal_lower or "usa" in journal_lower:
            return "United States"
        elif "british" in journal_lower or "uk" in journal_lower:
            return "United Kingdom"
        elif "chinese" in journal_lower or "china" in journal_lower:
            return "China"
        
        return None

    def papers_by_subject(
        self, papers: List[Paper], output_path: Optional[str] = None, top_n: int = 10
    ) -> str:
        """
        Generate chart showing papers by subject area.

        Args:
            papers: List of Paper objects
            output_path: Optional output path
            top_n: Number of top subjects to show

        Returns:
            Path to saved chart
        """
        if not papers:
            return ""

        # Extract subjects from papers
        subjects = []
        for paper in papers:
            paper_subjects = []
            
            # Method 1: Use subjects field if available (highest priority)
            if paper.subjects:
                for subject in paper.subjects:
                    if subject:
                        # Normalize subject names
                        normalized = self._normalize_subject(subject)
                        if normalized:
                            paper_subjects.append(normalized)
            
            # Method 2: Use keywords (second priority)
            if not paper_subjects and paper.keywords:
                normalized = [self._normalize_subject(kw) for kw in paper.keywords if kw]
                paper_subjects.extend([s for s in normalized if s])
            
            # Method 3: Infer from journal name (fallback)
            if not paper_subjects and paper.journal:
                inferred = self._infer_subject_from_journal(paper.journal)
                if inferred:
                    paper_subjects.append(inferred)
            
            # Method 4: Infer from abstract/title keywords (last resort)
            if not paper_subjects:
                # Try to extract key terms from title and abstract
                text_to_analyze = ""
                if paper.title:
                    text_to_analyze += paper.title.lower() + " "
                if paper.abstract:
                    text_to_analyze += paper.abstract.lower()
                
                if text_to_analyze:
                    # Check for specific health subcategories first
                    if any(term in text_to_analyze for term in ["health equity", "health disparities"]):
                        paper_subjects.append("Health Equity / Health Disparities")
                    elif any(term in text_to_analyze for term in ["health informatics", "digital health", "ehealth", "mhealth", "telemedicine"]):
                        paper_subjects.append("Health Informatics / Digital Health")
                    elif any(term in text_to_analyze for term in ["health communication"]):
                        paper_subjects.append("Health Communication")
                    elif any(term in text_to_analyze for term in ["health education"]):
                        paper_subjects.append("Health Education")
                    elif any(term in text_to_analyze for term in ["mental health"]):
                        paper_subjects.append("Mental Health")
                    elif any(term in text_to_analyze for term in ["public health"]):
                        paper_subjects.append("Public Health")
                    elif any(term in text_to_analyze for term in ["clinical medicine", "clinical"]):
                        paper_subjects.append("Clinical Medicine")
                    elif any(term in text_to_analyze for term in ["health", "medical", "clinical"]):
                        paper_subjects.append("Health Sciences")
                    elif any(term in text_to_analyze for term in ["ai", "machine learning", "llm", "chatbot"]):
                        paper_subjects.append("Artificial Intelligence")
                    elif any(term in text_to_analyze for term in ["nlp", "language model", "natural language"]):
                        paper_subjects.append("Natural Language Processing")
            
            subjects.extend(paper_subjects)

        if not subjects:
            # Fallback: Create placeholder chart
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(
                0.5,
                0.5,
                "Subject area data not available\n(requires keyword/journal categorization)",
                ha="center",
                va="center",
                fontsize=12,
            )
            ax.set_title("Documents by Subject Area", fontsize=14, fontweight="bold")
            ax.axis("off")

            if not output_path:
                output_path = self.output_dir / "papers_by_subject.png"
            else:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            plt.close()
            return str(output_path)

        # Count subjects
        subject_counts = Counter(subjects)
        top_subjects = subject_counts.most_common(top_n)

        if not top_subjects:
            return ""

        # Create chart
        subjects_list, counts_list = zip(*top_subjects)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        bars = ax.barh(range(len(subjects_list)), counts_list, color="steelblue", alpha=0.7)
        ax.set_yticks(range(len(subjects_list)))
        ax.set_yticklabels(subjects_list)
        ax.set_xlabel("Number of Papers", fontsize=12)
        ax.set_ylabel("Subject Area", fontsize=12)
        ax.set_title("Documents by Subject Area", fontsize=14, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)

        # Add value labels on bars
        for i, (subject, count) in enumerate(top_subjects):
            ax.text(count + 0.1, i, str(count), va="center", fontsize=10)

        plt.tight_layout()

        if not output_path:
            output_path = self.output_dir / "papers_by_subject.png"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)

    def _normalize_subject(self, keyword: str) -> str:
        """Normalize keyword to subject category using comprehensive taxonomy."""
        if not keyword:
            return ""
        
        keyword_lower = keyword.lower().strip()
        
        # Comprehensive subject mapping - ordered by specificity (most specific first)
        subject_mapping = [
            # Health/Medical Sciences - Specific subcategories first
            ("health equity", "Health Equity / Health Disparities"),
            ("health disparities", "Health Equity / Health Disparities"),
            ("health informatics", "Health Informatics / Digital Health"),
            ("digital health", "Health Informatics / Digital Health"),
            ("ehealth", "Health Informatics / Digital Health"),
            ("mhealth", "Health Informatics / Digital Health"),
            ("telemedicine", "Health Informatics / Digital Health"),
            ("health communication", "Health Communication"),
            ("health education", "Health Education"),
            ("mental health", "Mental Health"),
            ("public health", "Public Health"),
            ("health literacy", "Health Literacy"),
            ("clinical medicine", "Clinical Medicine"),
            ("clinical", "Clinical Medicine"),
            ("healthcare", "Health Sciences"),
            ("health care", "Health Sciences"),
            ("medical informatics", "Health Informatics / Digital Health"),
            ("medicine", "Health Sciences"),
            ("medical", "Health Sciences"),
            ("health", "Health Sciences"),
            ("biomedical", "Health Sciences"),
            ("epidemiology", "Public Health"),
            ("pharmacology", "Health Sciences"),
            ("nursing", "Health Sciences"),
            ("patient", "Health Sciences"),
            
            # Artificial Intelligence & Machine Learning
            ("large language model", "Artificial Intelligence"),
            ("llm", "Artificial Intelligence"),
            ("generative ai", "Artificial Intelligence"),
            ("chatbot", "Artificial Intelligence"),
            ("conversational ai", "Artificial Intelligence"),
            ("deep learning", "Machine Learning"),
            ("neural network", "Machine Learning"),
            ("machine learning", "Machine Learning"),
            ("artificial intelligence", "Artificial Intelligence"),
            ("ai", "Artificial Intelligence"),
            ("ml", "Machine Learning"),
            
            # Natural Language Processing
            ("natural language processing", "Natural Language Processing"),
            ("nlp", "Natural Language Processing"),
            ("language model", "Natural Language Processing"),
            ("text mining", "Natural Language Processing"),
            ("computational linguistics", "Natural Language Processing"),
            ("speech recognition", "Natural Language Processing"),
            
            # Computer Science
            ("computer science", "Computer Science"),
            ("software engineering", "Computer Science"),
            ("information systems", "Computer Science"),
            ("data science", "Computer Science"),
            ("cybersecurity", "Computer Science"),
            ("software", "Computer Science"),
            ("algorithm", "Computer Science"),
            ("programming", "Computer Science"),
            ("computing", "Computer Science"),
            
            # Social Sciences
            ("social science", "Social Sciences"),
            ("sociology", "Social Sciences"),
            ("psychology", "Social Sciences"),
            ("behavioral", "Social Sciences"),
            ("behavior", "Social Sciences"),
            ("social", "Social Sciences"),
            ("anthropology", "Social Sciences"),
            ("economics", "Social Sciences"),
            
            # Education
            ("education", "Education"),
            ("pedagogy", "Education"),
            ("learning", "Education"),
            ("teaching", "Education"),
            
            # Engineering
            ("engineering", "Engineering"),
            ("electrical engineering", "Engineering"),
            ("mechanical engineering", "Engineering"),
            
            # Mathematics & Statistics
            ("mathematics", "Mathematics"),
            ("statistics", "Mathematics"),
            ("statistical", "Mathematics"),
            ("math", "Mathematics"),
            
            # Biology & Life Sciences
            ("biology", "Life Sciences"),
            ("biochemistry", "Life Sciences"),
            ("genetics", "Life Sciences"),
            ("molecular biology", "Life Sciences"),
            
            # Physics
            ("physics", "Physics"),
            ("quantum", "Physics"),
            
            # Chemistry
            ("chemistry", "Chemistry"),
            ("chemical", "Chemistry"),
        ]

        # Check for matches (most specific first)
        for pattern, category in subject_mapping:
            if pattern in keyword_lower:
                return category

        # Return capitalized keyword if no match
        return keyword.strip().title()

    def _infer_subject_from_journal(self, journal: str) -> Optional[str]:
        """Infer subject from journal name using comprehensive patterns."""
        if not journal:
            return None
        
        journal_lower = journal.lower()
        
        # Health/Medical journals
        health_terms = ["health", "medical", "medicine", "clinical", "biomedical", 
                       "pharmacy", "nursing", "public health", "epidemiology",
                       "healthcare", "health care", "the lancet", "nejm", "jama",
                       "bmj", "nature medicine", "plos medicine"]
        if any(term in journal_lower for term in health_terms):
            return "Health Sciences"
        
        # AI/ML journals
        ai_terms = ["artificial intelligence", "machine learning", "ai", "ml",
                   "neural", "deep learning", "ieee transactions on neural",
                   "jmlr", "icml", "neurips", "aaai", "ijcai"]
        if any(term in journal_lower for term in ai_terms):
            return "Artificial Intelligence"
        
        # NLP journals
        nlp_terms = ["nlp", "natural language", "computational linguistics",
                    "acl", "emnlp", "naacl", "computational linguistics",
                    "language processing", "speech"]
        if any(term in journal_lower for term in nlp_terms):
            return "Natural Language Processing"
        
        # Computer Science journals
        cs_terms = ["computer science", "computing", "software", "ieee transactions",
                   "acm", "information systems", "data science", "cybersecurity"]
        if any(term in journal_lower for term in cs_terms):
            return "Computer Science"
        
        # Social Sciences journals
        social_terms = ["social science", "sociology", "psychology", "behavioral",
                       "anthropology", "economics", "social research"]
        if any(term in journal_lower for term in social_terms):
            return "Social Sciences"
        
        # Education journals
        education_terms = ["education", "pedagogy", "learning", "teaching",
                          "educational", "instructional"]
        if any(term in journal_lower for term in education_terms):
            return "Education"
        
        return None

    def network_graph(self, papers: List[Paper], output_path: Optional[str] = None) -> str:
        """
        Generate interactive network visualization based on similarity using Pyvis.

        Args:
            papers: List of Paper objects
            output_path: Optional output path (will generate HTML file)

        Returns:
            Path to saved HTML file
        """
        try:
            import networkx as nx
        except ImportError:
            print("NetworkX not installed. Skipping network graph.")
            return ""

        try:
            from pyvis.network import Network
        except ImportError:
            print("Pyvis not installed. Install with: pip install pyvis")
            return ""

        if not papers or len(papers) < 2:
            return ""

        # Create graph
        G = nx.Graph()

        # Add nodes (papers)
        for i, paper in enumerate(papers):
            G.add_node(i, title=paper.title if paper.title else f"Paper {i+1}")

        # Build similarity matrix
        similarity_matrix = self._compute_similarity_matrix(papers)

        # Add edges based on similarity
        threshold = 0.1  # Minimum similarity to create edge
        for i in range(len(papers)):
            for j in range(i + 1, len(papers)):
                similarity = similarity_matrix[i][j]
                if similarity > threshold:
                    G.add_edge(i, j, weight=similarity)

        # If no edges created, create minimal spanning tree to ensure connectivity
        if G.number_of_edges() == 0:
            # Use keyword/author overlap as fallback
            for i in range(len(papers)):
                for j in range(i + 1, len(papers)):
                    overlap = self._compute_overlap(papers[i], papers[j])
                    if overlap > 0:
                        G.add_edge(i, j, weight=overlap)

        if G.number_of_edges() == 0:
            # Last resort: connect sequentially
            for i in range(len(papers) - 1):
                G.add_edge(i, i + 1, weight=0.1)

        # Determine output path
        if not output_path:
            output_path = self.output_dir / "network_graph.html"
        else:
            output_path = Path(output_path)
            # Change extension to .html if needed
            if output_path.suffix == ".png":
                output_path = output_path.with_suffix(".html")
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create Pyvis network
        net = Network(
            height="800px",
            width="100%",
            notebook=False,
            directed=False,
            bgcolor="#ffffff",
            font_color="#000000"
        )

        # Configure physics for better layout
        net.set_options("""
        {
          "physics": {
            "enabled": true,
            "barnesHut": {
              "gravitationalConstant": -2000,
              "centralGravity": 0.1,
              "springLength": 200,
              "springConstant": 0.04,
              "damping": 0.09
            },
            "stabilization": {
              "enabled": true,
              "iterations": 200
            }
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 200,
            "hideEdgesOnDrag": false,
            "hideNodesOnDrag": false
          }
        }
        """)

        # Color nodes by year if available
        years = [p.year for p in papers]
        has_years = any(years)
        
        if has_years:
            min_year = min(y for y in years if y)
            max_year = max(y for y in years if y)
            year_range = max_year - min_year if max_year > min_year else 1
        
        # Color palette for years (viridis-like colors)
        year_colors = [
            "#440154", "#482777", "#3f4a8a", "#31688e", "#26828e",
            "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fee825"
        ]

        # Add nodes with full information
        for i, paper in enumerate(papers):
            # Create label (shortened for display)
            label = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            
            # Create tooltip with full information
            tooltip_parts = [f"<b>{paper.title}</b>"]
            if paper.authors:
                authors_str = ", ".join(paper.authors[:3])
                if len(paper.authors) > 3:
                    authors_str += f" et al. ({len(paper.authors)} authors)"
                tooltip_parts.append(f"Authors: {authors_str}")
            if paper.year:
                tooltip_parts.append(f"Year: {paper.year}")
            if paper.journal:
                tooltip_parts.append(f"Journal: {paper.journal}")
            tooltip = "<br>".join(tooltip_parts)
            
            # Determine node color
            if has_years and paper.year:
                # Map year to color index
                normalized = (paper.year - min_year) / year_range if year_range > 0 else 0.5
                color_idx = min(int(normalized * (len(year_colors) - 1)), len(year_colors) - 1)
                node_color = year_colors[color_idx]
            else:
                node_color = "#808080"  # Gray for unknown year
            
            # Calculate node size based on degree (connectivity)
            degree = G.degree(i)
            node_size = 20 + (degree * 3)  # Base size + connectivity bonus
            
            # Add node
            net.add_node(
                i,
                label=label,
                title=tooltip,
                color=node_color,
                size=node_size,
                url=paper.url if paper.url else None,
                shape="dot"
            )

        # Add edges with weights
        edges = G.edges(data=True)
        max_weight = max((data.get("weight", 0.1) for _, _, data in edges), default=1.0)
        
        for u, v, data in edges:
            weight = data.get("weight", 0.1)
            # Scale edge width based on weight
            width = max(1, int(weight * 10 / max_weight))
            net.add_edge(u, v, value=weight, width=width, color={"color": "#848484", "highlight": "#000000"})

        # Save network
        net.save_graph(str(output_path))
        
        # Also generate a static PNG version for compatibility
        png_path = output_path.with_suffix(".png")
        try:
            # Try to generate a static version using matplotlib as fallback
            import matplotlib.pyplot as plt
            pos = nx.spring_layout(G, k=2, iterations=100, seed=42)
            
            fig, ax = plt.subplots(figsize=(14, 10))
            
            # Draw edges
            edges_list = list(G.edges())
            weights_list = [G[u][v].get("weight", 0.1) for u, v in edges_list]
            nx.draw_networkx_edges(G, pos, alpha=0.3, width=[w * 2 for w in weights_list], ax=ax)
            
            # Draw nodes
            node_colors_list = []
            for i, paper in enumerate(papers):
                if has_years and paper.year:
                    normalized = (paper.year - min_year) / year_range if year_range > 0 else 0.5
                    node_colors_list.append(normalized)
                else:
                    node_colors_list.append(0.5)
            
            nx.draw_networkx_nodes(
                G, pos, node_color=node_colors_list, node_size=800,
                cmap=plt.cm.viridis, alpha=0.8, ax=ax
            )
            
            # Draw labels
            labels = {i: papers[i].title[:30] + "..." if len(papers[i].title) > 30 else papers[i].title
                     for i in range(len(papers))}
            nx.draw_networkx_labels(G, pos, labels, font_size=7, ax=ax)
            
            ax.set_title("Network Visualization (Similarity-Based)\nInteractive version: " + str(output_path.name), 
                        fontsize=14, fontweight="bold")
            ax.axis("off")
            
            plt.tight_layout()
            plt.savefig(png_path, dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            # If PNG generation fails, that's okay - HTML is the primary output
            logger.warning(f"Could not generate PNG version: {e}")

        return str(output_path)

    def _compute_similarity_matrix(self, papers: List[Paper]) -> List[List[float]]:
        """Compute similarity matrix between papers."""
        n = len(papers)
        similarity_matrix = [[0.0] * n for _ in range(n)]

        if SKLEARN_AVAILABLE:
            # Use TF-IDF for abstract similarity
            abstracts = [p.abstract or "" for p in papers]
            if any(abstracts):
                try:
                    vectorizer = TfidfVectorizer(max_features=100, stop_words="english")
                    tfidf_matrix = vectorizer.fit_transform(abstracts)
                    cosine_sim = cosine_similarity(tfidf_matrix)
                    
                    for i in range(n):
                        for j in range(n):
                            similarity_matrix[i][j] = float(cosine_sim[i][j])
                except Exception:
                    # Fallback to keyword/author overlap
                    pass

        # Enhance with keyword and author overlap
        for i in range(n):
            for j in range(i + 1, n):
                overlap_score = self._compute_overlap(papers[i], papers[j])
                # Combine TF-IDF similarity (if available) with overlap
                if similarity_matrix[i][j] == 0.0:
                    similarity_matrix[i][j] = overlap_score
                else:
                    similarity_matrix[i][j] = (similarity_matrix[i][j] * 0.7) + (overlap_score * 0.3)
                similarity_matrix[j][i] = similarity_matrix[i][j]

        return similarity_matrix

    def _compute_overlap(self, paper1: Paper, paper2: Paper) -> float:
        """Compute overlap score between two papers based on keywords and authors."""
        score = 0.0
        
        # Keyword overlap
        if paper1.keywords and paper2.keywords:
            keywords1 = set(kw.lower() for kw in paper1.keywords)
            keywords2 = set(kw.lower() for kw in paper2.keywords)
            if keywords1 or keywords2:
                overlap = len(keywords1 & keywords2)
                union = len(keywords1 | keywords2)
                if union > 0:
                    score += (overlap / union) * 0.5
        
        # Author overlap
        if paper1.authors and paper2.authors:
            authors1 = set(a.lower() for a in paper1.authors)
            authors2 = set(a.lower() for a in paper2.authors)
            if authors1 or authors2:
                overlap = len(authors1 & authors2)
                union = len(authors1 | authors2)
                if union > 0:
                    score += (overlap / union) * 0.5
        
        return min(score, 1.0)

    def generate_risk_of_bias_plot(
        self,
        assessments: List[Dict[str, Any]],
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate traffic light style risk of bias plot.

        Args:
            assessments: List of risk of bias assessments with domains and ratings
            output_path: Optional output path (default: auto-generated)

        Returns:
            Path to saved chart
        """
        if not assessments:
            return ""

        # Prepare data for plotting
        study_ids = []
        domains = []
        ratings = []

        for assessment in assessments:
            study_id = assessment.get("study_id", "Unknown")
            domains_dict = assessment.get("domains", {})
            
            for domain, rating in domains_dict.items():
                study_ids.append(study_id)
                domains.append(domain[:30])  # Truncate long domain names
                ratings.append(rating)

        if not study_ids:
            return ""

        # Create DataFrame
        df = pd.DataFrame({
            "Study": study_ids,
            "Domain": domains,
            "Rating": ratings
        })

        # Map ratings to colors and numeric values
        rating_map = {
            "Low": (0, 1, 0),  # Green
            "Some concerns": (1, 1, 0),  # Yellow
            "High": (1, 0.5, 0),  # Orange
            "Critical": (1, 0, 0),  # Red
        }

        # Get unique studies and domains
        unique_studies = df["Study"].unique()
        unique_domains = df["Domain"].unique()

        # Create figure
        fig, ax = plt.subplots(figsize=(max(8, len(unique_studies) * 0.8), max(6, len(unique_domains) * 0.6)))
        
        # Create grid for traffic lights
        y_positions = {domain: i for i, domain in enumerate(unique_domains)}
        x_positions = {study: i for i, study in enumerate(unique_studies)}

        # Plot traffic lights
        for _, row in df.iterrows():
            study_idx = x_positions[row["Study"]]
            domain_idx = y_positions[row["Domain"]]
            rating = row["Rating"]
            
            color = rating_map.get(rating, (0.5, 0.5, 0.5))  # Gray for unknown
            circle = plt.Circle((study_idx, domain_idx), 0.3, color=color, zorder=2)
            ax.add_patch(circle)

        # Set labels and ticks
        ax.set_xticks(range(len(unique_studies)))
        ax.set_xticklabels(unique_studies, rotation=45, ha="right")
        ax.set_yticks(range(len(unique_domains)))
        ax.set_yticklabels(unique_domains)
        ax.set_xlabel("Study", fontsize=12)
        ax.set_ylabel("Risk of Bias Domain", fontsize=12)
        ax.set_title("Risk of Bias Assessment (Traffic Light Plot)", fontsize=14, fontweight="bold")
        ax.set_xlim(-0.5, len(unique_studies) - 0.5)
        ax.set_ylim(-0.5, len(unique_domains) - 0.5)
        ax.grid(True, alpha=0.3)

        # Add legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=color, label=rating)
            for rating, color in rating_map.items()
        ]
        ax.legend(handles=legend_elements, loc="upper left", bbox_to_anchor=(1, 1))

        plt.tight_layout()

        # Save
        if not output_path:
            output_path = self.output_dir / "risk_of_bias_plot.png"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)

    def generate_grade_evidence_profile(
        self,
        assessments: List[Dict[str, Any]],
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate GRADE evidence profile visualization.

        Args:
            assessments: List of GRADE assessments with outcomes and certainty ratings
            output_path: Optional output path (default: auto-generated)

        Returns:
            Path to saved chart
        """
        if not assessments:
            return ""

        # Prepare data
        outcomes = []
        certainty_levels = []
        certainty_numeric = []

        certainty_map = {
            "High": 4,
            "Moderate": 3,
            "Low": 2,
            "Very Low": 1,
        }

        for assessment in assessments:
            outcome = assessment.get("outcome", "Unknown")
            certainty = assessment.get("certainty", "")
            outcomes.append(outcome[:40])  # Truncate long outcome names
            certainty_levels.append(certainty)
            certainty_numeric.append(certainty_map.get(certainty, 0))

        if not outcomes:
            return ""

        # Create figure
        fig, ax = plt.subplots(figsize=(10, max(6, len(outcomes) * 0.8)))

        # Create horizontal bar chart
        y_pos = range(len(outcomes))
        colors = []
        for certainty in certainty_levels:
            if certainty == "High":
                colors.append((0, 0.8, 0))  # Green
            elif certainty == "Moderate":
                colors.append((0.8, 0.8, 0))  # Yellow
            elif certainty == "Low":
                colors.append((1, 0.5, 0))  # Orange
            elif certainty == "Very Low":
                colors.append((1, 0, 0))  # Red
            else:
                colors.append((0.5, 0.5, 0.5))  # Gray

        bars = ax.barh(y_pos, certainty_numeric, color=colors, alpha=0.7)

        # Set labels
        ax.set_yticks(y_pos)
        ax.set_yticklabels(outcomes)
        ax.set_xlabel("Certainty Level", fontsize=12)
        ax.set_ylabel("Outcome", fontsize=12)
        ax.set_title("GRADE Evidence Profile", fontsize=14, fontweight="bold")
        ax.set_xlim(0, 5)
        ax.set_xticks([1, 2, 3, 4])
        ax.set_xticklabels(["Very Low", "Low", "Moderate", "High"])

        # Add value labels on bars
        for i, (bar, certainty) in enumerate(zip(bars, certainty_levels)):
            width = bar.get_width()
            ax.text(width + 0.1, bar.get_y() + bar.get_height() / 2,
                   certainty, ha="left", va="center", fontweight="bold")

        plt.tight_layout()

        # Save
        if not output_path:
            output_path = self.output_dir / "grade_evidence_profile.png"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(output_path)
