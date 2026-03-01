"""RAG module: chunking, embedding, and semantic retrieval for writing phase."""

from src.rag.chunker import chunk_extraction_record
from src.rag.embedder import embed_texts
from src.rag.retriever import RAGRetriever

__all__ = ["chunk_extraction_record", "embed_texts", "RAGRetriever"]
