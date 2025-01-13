"""
Module for performing initial Gmail account handshake and data extraction.

This module handles the initial connection with a user's Gmail account, extracting sent emails,
storing them in a vector database, and creating a user profile through email analysis.
"""
import logging
from typing import List, Dict, Any
from urllib.parse import quote_plus

from email_adapt.database.vector_store import VectorStore
from email_adapt.gmail.src.extract_body import ExtractUserBodyFromEmail
from email_adapt.gmail.src.api.threads import GmailThreadExtractor
from email_adapt.gmail.src.user_profile import UserProfile

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class InitialHandshake:
    """
    Handles the initial setup and data extraction from a user's Gmail account.
    """

    def __init__(self, email_address: str):
        """
        Initialize the handshake process with a Gmail account.

        :param email_address: The Gmail address to process
        """
        logger.info(f"Starting handshake process for email: {email_address}")

        self.email_address = email_address
        self.safe_email_address = quote_plus(email_address)
        # Use the vector store for RAG purposes
        self.vector_store = VectorStore(collection_name=self.safe_email_address, overwrite=True)
        self.user_profile = UserProfile(vector_store=self.vector_store)

    def get_threads(self, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve email threads from the user's Gmail account.

        :param max_results: Maximum number of threads to retrieve
        """
        logger.debug(f"[{self.__class__.__name__}] Retrieving up to {max_results} threads")
        try:
            threads = GmailThreadExtractor(email_address=self.email_address).get_threads(max_results=max_results)
            logger.info(f"[{self.__class__.__name__}] Successfully retrieved {len(threads)} threads")
            return threads
        except FileNotFoundError as e:
            logger.error(f"[{self.__class__.__name__}] Credentials file not founds: {str(e)}")
            raise

    def get_email_bodies(self, threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract email body content from threads.

        :param threads: List of thread data
        """
        logger.debug("Extracting email bodies from threads")
        try:
            body_extractor = ExtractUserBodyFromEmail(email_address=self.email_address)
            email_bodies = body_extractor.extract(threads)
            logger.info(f"[{self.__class__.__name__}] Successfully extracted {len(email_bodies)} email bodies")
            return email_bodies
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to extract email bodies: {str(e)}")
            raise

    def index_email_bodies(self, email_bodies: List[Dict[str, Any]]) -> None:
        """
        Index email bodies in the vector database.

        :param email_bodies: Email bodies to index
        """
        logger.info(f"Indexing email bodies for {self.safe_email_address}")
        try:
            # Prepare data for indexing
            texts = [
                v["content"] for refs in email_bodies 
                for k, v in refs.items() if "body_reference" in k
            ]
            metadata = [
                {
                    "thread_id": k,
                    "date": v.get("date", ""),
                    "from": v.get("from", ""),
                    "to": v.get("to", ""),
                    "subject": v.get("subject", ""),
                    "body": v.get("body", ""),
                    "labelIds": v.get("labelIds", []),
                    "is_forwarded": v.get("is_forwarded", False),
                }
                for refs in email_bodies
                for k, v in refs.items()
                if "body_reference" in k
            ]

            self.vector_store.index(texts, metadata)
            logger.info(f"[{self.__class__.__name__}] Successfully indexed {len(texts)} email bodies")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to index email bodies: {str(e)}")
            raise

    
    def __call__(self) -> None:
        """
        Perform the initial handshake process.

        :param overwrite: Whether to overwrite the existing collections. This is for development purposes.  
        """
        threads = self.get_threads()
        # Store the email bodies in the vector database
        self.index_email_bodies(email_bodies = self.get_email_bodies(threads))
        # Create the user profile. Pick the top_k most recent emails.
        try:
            self.user_profile.create_user_profile(
                metadata_filter={"is_forwarded": False},
                top_k=30,
                weight_recency=1.0,
                weight_length=0.0
            )
            logger.info(f"[{self.__class__.__name__}] Successfully created {self.safe_email_address} profile")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to create {self.safe_email_address} profile: {str(e)}")
            raise


if __name__ == "__main__":
    l = InitialHandshake(email_address="medsriha@gmail.com")
    l()
