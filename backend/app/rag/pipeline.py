"""Simple placeholder RAG pipeline.

This module provides a minimal `RAGPipeline` class so imports like
`from ..rag.pipeline import RAGPipeline` succeed during development.

Fill with the real retrieval / generation logic later.
"""
from typing import Any


class RAGPipeline:
    """Minimal RAG pipeline placeholder.

    Contract:
    - input: text (str)
    - output: answer (str)
    Error modes: None raised here; callers should handle application-level errors.
    """

    def __init__(self) -> None:
        # Initialize any heavy components lazily in real implementation.
        pass

    def query(self, text: str) -> str:
        """Query the pipeline with `text` and return a textual answer.

        Current implementation is intentionally minimal and returns an empty
        string (initial version of the RAG pipeline).
        """
        # FUTURE: wire up retriever + generator; return a useful answer.
        return ""
