from datetime import datetime
from typing import Any, Dict, List, Optional

from email_adapt.gmail.src.database.vector_database import QueryEngine


class UserEmailStyle:
    """Use email references for RAG purposes to provide the LLM with context"""

    def __init__(self, collection_name: str):
        self.database = QueryEngine(collection_name=collection_name)

    @staticmethod
    def _rank_references(
        references: List[Dict[str, Any]], weight_recency: float = 0.3, weight_length: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Ranks email references based on recency and text length.
        Returns a sorted list with most recent and longest texts prioritized.
        """

        def parse_date(date_str):
            try:
                return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
            except ValueError:
                # Return a very old date if parsing fails
                return datetime.min

        max_length = 0

        for text in references:
            max_length = max(max_length, len(text["text"]))

        # Calculate a score for each reference
        # Score = recency_weight * recency_score + length_weight * length_score
        for ref in references:
            date = parse_date(ref["metadata"]["date"])
            text_length = len(ref["text"])

            # Normalize scores between 0 and 1
            now = datetime.now()
            time_diff = (now - date.replace(tzinfo=None)).total_seconds()
            recency_score = 1 / (1 + time_diff / 86400)  # 86400 seconds in a day

            # Assuming max text length of 10000 characters
            length_score = text_length / max_length

            # Combine scores (giving more weight to recency)
            ref["rank_score"] = (weight_recency * recency_score) + (weight_length * length_score)

        return sorted(references, key=lambda x: x["rank_score"], reverse=True)

    def get_references(self, top_k: int = 5, metadata_filter: Optional[dict] = {"is_forwarded": False}) -> List[str]:
        emails = self.database.search(metadata_filter=metadata_filter)
        ranked_emails = self._rank_references(emails)
        return ranked_emails[:top_k]
