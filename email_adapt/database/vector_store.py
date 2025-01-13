import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from haystack.components.embedders import SentenceTransformersTextEmbedder
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    text: str
    score: float
    metadata: Dict[str, Any]


class VectorStore:
    """Class to create, delete, index and search collections in the vector database
    """

    def __init__(
        self,
        collection_name: str,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_size: int = 384,
        overwrite: bool = False,
    ):
        """Initialize the VectorStore class.

        :param collection_name: The name of the collection to store the data in
        :param embedding_model: The model to use for embedding
        :param overwrite: Whether to overwrite the existing collection
        """
        self.collection_name = collection_name
        self.embedding_size = embedding_size
        self._initialize_embedder(embedding_model)

        db_path = Path(__file__).parent.parent.parent.parent / "storage" / collection_name
        self._init_client(db_path)

        if overwrite:
            self._delete_collection()
            self._create_collection()

    def _init_client(self, db_path: Path) -> None:
        """Initialize the Qdrant client

        :param db_path: The path to the vector database.
        """
        try:
            self.client = QdrantClient(path=str(db_path))
            logger.info(f"[{self.__class__.__name__}] Initialized Qdrant client: {self.collection_name}")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Qdrant client initialization failed: {e}")
            raise

    def _initialize_embedder(self, embedding_model: str) -> None:
        """Lazy initialization of the embedding model

        :param embedding_model: The model to use for embedding
        """
        try:
            logger.info(f"Initializing embedding model: {embedding_model}")
            self.embedder = SentenceTransformersTextEmbedder(model=embedding_model)
            self.embedder.warm_up()
            logger.info(f"[{self.__class__.__name__}] Successfully warmed up embedding model")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to initialize embedding model: {e}")
            raise

    def _embed(self, text: str) -> List[float]:
        """Generate embedding using the model

        :param text: The text to embed
        """
        # Convert text to string if it isn't already
        text = str(text) if not isinstance(text, str) else text
        logger.debug(f"Generating embedding for text: {text[:50]}...")
        try:
            embedding = self.embedder.run(text)["embedding"]
            logger.debug(f"[{self.__class__.__name__}] Successfully generated embedding of size {len(embedding)}")
            return embedding
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to generate embedding: {e}")
            raise

    def _create_collection(self) -> None:
        """Create a new collection if it doesn't exist"""
        logger.info(f"[{self.__class__.__name__}] Attempting to create collection: {self.collection_name}")
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=self.embedding_size, distance=models.Distance.COSINE),
            )
            logger.info(
                f"[{self.__class__.__name__}] Successfully created collection: {self.collection_name} with size {self.embedding_size}"
            )
        except Exception as e:
            logger.warning(f"[{self.__class__.__name__}] Collection creation issue: {e}")

    def _delete_collection(self) -> bool:
        """Delete the entire collection from the vector database."""
        logger.info(f"[{self.__class__.__name__}] Attempting to delete collection: {self.collection_name}")

        try:
            self.client.delete_collection(collection_name=self.collection_name)
            logger.info(f"[{self.__class__.__name__}] Successfully deleted collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to delete collection {self.collection_name}: {e}")
            return False

    def index(self, texts: List[str], metadata: Optional[List[dict]] = None):
        """Add texts and their embeddings to the collection"""
        logger.info(f"[{self.__class__.__name__}] Indexing {len(texts)} texts")

        if metadata is None:
            metadata = [{} for _ in texts]
            logger.debug(f"[{self.__class__.__name__}]  No metadata provided, using empty dictionaries")

        try:
            # Generate embeddings for all texts
            logger.debug(f"[{self.__class__.__name__}]  Generating embeddings for all texts")
            embeddings = []
            for i, text in enumerate(texts):
                logger.debug(f"[{self.__class__.__name__}]  Processing text {i+1}/{len(texts)}")
                embedding = self._embed(text)
                embeddings.append(embedding)

            # Prepare points for insertion
            logger.debug(f"[{self.__class__.__name__}]  Preparing points for insertion")
            points = [
                models.PointStruct(id=i, vector=embedding, payload={"text": text, **meta})
                for i, (text, embedding, meta) in enumerate(zip(texts, embeddings, metadata))
            ]

            # Upload points to collection
            logger.info(
                f"[{self.__class__.__name__}]  Uploading {len(points)} points to collection {self.collection_name}"
            )
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"[{self.__class__.__name__}]  Successfully indexed {len(points)} texts")

        except Exception as e:
            logger.error(f"[{self.__class__.__name__}]  Failed to index texts: {e}")
            raise

    def search(
        self,
        top_k: Optional[int] = None,
        query: Optional[str] = None,
        metadata_filter: Optional[dict] = None,
        weight_recency: Optional[float] = None,
        weight_length: Optional[float] = None,
    ) -> List[SearchResult]:
        """Search for similar texts using a query and optional metadata filters
        """
        if not query:
            all_emails = self._get_all_emails(metadata_filter)
            if all_emails:
                if weight_recency or weight_length:
                    return self._rank_emails(all_emails, top_k, weight_recency or 0, weight_length or 0)
                else:
                    return all_emails
            else:
                return []

        try:
            search_params = self._build_search_params(query, metadata_filter)
            search_results = self.client.search(collection_name=self.collection_name, limit=top_k, **search_params)

            results = [
                SearchResult(
                    text=result.payload["text"],
                    score=result.score,
                    metadata={k: v for k, v in result.payload.items() if k != "text"},
                )
                for result in search_results
            ]

            if weight_recency or weight_length:
                return self._rank_emails(results, top_k, weight_recency, weight_length)
            else:
                return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def _build_search_params(self, query: str, metadata_filter: Optional[dict]) -> Dict[str, Any]:
        """Build search parameters including filters and query vector"""
        params = {"query_vector": self._embed(query)}

        if metadata_filter:
            filter_conditions = [
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
                for key, value in metadata_filter.items()
            ]
            params["query_filter"] = models.Filter(must=filter_conditions)

        return params

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse date string to datetime object"""
        try:
            return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            return datetime.min

    def _rank_emails(
        self,
        emails: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        weight_recency: float = 0,
        weight_length: float = 0,
    ) -> List[Dict[str, Any]]:
        """Ranks emails based on recency and text length.
        Returns a sorted list with most recent and longest emails prioritized.

        :param emails: List of dictionaries with 'text' and 'metadata' keys
        :param top_k: Optional integer to limit the number of results
        :param weight_recency: Float between 0 and 1 to weight recency
        :param weight_length: Float between 0 and 1 to weight length
        """
        if not weight_recency and not weight_length:
            return emails[:top_k] if top_k else emails

        max_length = max(len(email.get("text", "")) for email in emails)

        # Calculate a score for each reference
        for email in emails:
            if weight_length > 0:
                text_length = len(email.get("text", ""))
                length_score = text_length / max_length
            else:
                length_score = 0

            if weight_recency > 0:
                date = self._parse_date(email.get("metadata", {}).get("date", ""))
                if date:
                    now = datetime.now()
                    time_diff = (now - date.replace(tzinfo=None)).total_seconds()
                    # Normalize scores between 0 and 1
                    recency_score = 1 / (1 + time_diff / 86400)
                else:
                    recency_score = 0
            else:
                recency_score = 0

            # Add rank_score to the SearchResult object
            email["rank_score"] = (weight_recency * recency_score) + (weight_length * length_score)

        sorted_emails = sorted(emails, key=lambda x: x["rank_score"], reverse=True)
        return sorted_emails[:top_k] if top_k else sorted_emails

    def _get_all_emails(self, metadata_filter: Optional[dict] = None) -> List[SearchResult]:
        """Retrieve all emails and their metadata from the vector database

        :param metadata_filter: Optional dictionary of metadata key-value pairs to filter by
        """
        logger.info(f"Retrieving emails from collection: {self.collection_name} with filters: {metadata_filter}")

        try:
            # Prepare filter if metadata filtering is requested
            scroll_params = {
                "collection_name": self.collection_name,
                "limit": 100,  # Process in batches of 100
                "with_payload": True,
                "with_vectors": False,  # We don't need the vectors
            }

            if metadata_filter:
                filter_conditions = []
                for key, value in metadata_filter.items():
                    filter_conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
                scroll_params["scroll_filter"] = models.Filter(must=filter_conditions)

            # Initial scroll
            scroll_results = self.client.scroll(**scroll_params)

            all_results = []
            while True:
                records, next_page_offset = scroll_results

                # Process current batch
                batch_results = [
                    {
                        "text": record.payload["text"],
                        "metadata": {k: v for k, v in record.payload.items() if k != "text"},
                    }
                    for record in records
                ]
                all_results.extend(batch_results)

                # Break if no more results
                if next_page_offset is None:
                    break

                # Get next batch
                scroll_params["offset"] = next_page_offset
                scroll_results = self.client.scroll(**scroll_params)

            logger.info(f"[{self.__class__.__name__}] There are {len(all_results)} emails in the database")

            return all_results

        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to retrieve emails: {e}")
            raise

