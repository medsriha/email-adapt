import json
import logging
from pathlib import Path
from typing import Any, ClassVar, Dict, List
from urllib.parse import quote_plus

import tiktoken

from email_adapt.gmail.src.utils.threads_utils import clean_text, parse_from_field

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ExtractUserBodyFromEmail:
    """Extract user body from email and store it on disk."""

    PROHIBITED_SUBJECTS: ClassVar[List[str]] = ["unsubscribe", "list-unsubscribe"]
    # Add new constants
    MIN_BODY_LENGTH: ClassVar[int] = 1
    TOKEN_FALLBACK_CHARS: ClassVar[int] = 4

    def __init__(self, email_address: str, openai_model: str = "gpt-4o"):
        """Initialize the extractor.

        Args:
            email_address: Email address to filter messages from
            openai_model: OpenAI model name for token counting
        """
        logger.info(f"Initializing {self.__class__.__name__} with email: {email_address}, model: {openai_model}")

        self.email_address = email_address
        self.openai_model = openai_model
        self.references_dir = (
            Path(__file__).parent.parent.parent / "data" / quote_plus(self.email_address) / "references"
        )
        logger.debug(f"[{self.__class__.__name__}] References directory set to: {self.references_dir}")

    def _get_token_count(self, text: str) -> int:
        """Get the token count of the text using OpenAI's tokenizer.

        :param text: The text to count tokens for.
        """
        try:
            encoding = tiktoken.encoding_for_model(self.openai_model)
            token_count = len(encoding.encode(text))
            logger.debug(f"[{self.__class__.__name__}] Token count for text: {token_count}")
            return token_count
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] Error getting token count: {e}. Fallback to rough estimation with {self.TOKEN_FALLBACK_CHARS} characters per token."
            )
            # Fallback: rough estimation (1 token ≈ 4 characters)
            return len(text) // self.TOKEN_FALLBACK_CHARS

    def _is_valid_email(self, email: Dict[str, Any], subject: str) -> bool:
        """Check if email meets all validity criteria.

        Args:
            email: Email message dictionary
            subject: Cleaned subject line

        Returns:
            bool: True if email is valid for processing
        """
        is_valid = (
            not any(prohibited in subject for prohibited in self.PROHIBITED_SUBJECTS)
            and not email.get("is_forwarded", False)
            and len(clean_text(email.get("body", ""))) >= self.MIN_BODY_LENGTH
        )
        logger.debug(f"[{self.__class__.__name__}] Email validity check - Subject: {subject}, Is valid: {is_valid}")
        return is_valid

    def _process_single_thread(self, thread: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single thread and extract body references.

        Args:
            thread: Thread dictionary containing messages

        Returns:
            Dict containing thread_id and body references
        """
        thread_id = thread.get("thread_id")
        if not thread_id:
            logger.error(f"[{self.__class__.__name__}] Thread missing thread_id")
            raise ValueError("Thread missing thread_id")

        logger.info(f"[{self.__class__.__name__}] Processing thread: {thread_id}")
        body_reference = {"thread_id": thread_id}
        counter = 1

        for email in thread.get("messages", []):
            _, email_address = parse_from_field(email.get("from", ""))

            if email_address != self.email_address:
                logger.debug(f"[{self.__class__.__name__}] Skipping email from different address: {email_address}")
                continue

            subject = email.get("subject", "").lower()
            if not self._is_valid_email(email, subject):
                logger.debug(f"[{self.__class__.__name__}] Skipping invalid email with subject: {subject}")
                continue

            cleaned_body = clean_text(email.get("body", ""))
            message_id = email.get("message_id", "")
            token_count = self._get_token_count(cleaned_body)

            logger.debug(f"[{self.__class__.__name__}] Processing message {message_id} with {token_count} tokens")

            body_reference[f"body_reference_{counter}"] = {
                "content": cleaned_body,
                "cost": token_count,
                "message_id": message_id,
                "date": email.get("date", ""),
                "from": email.get("from", ""),
                "to": email.get("to", ""),
                "subject": email.get("subject", ""),
                "body": email.get("body", ""),
                "labelIds": email.get("labelIds", ""),
                "is_forwarded": email.get("is_forwarded", ""),
            }
            counter += 1

        logger.info(f"[{self.__class__.__name__}] Processed thread {thread_id} with {counter-1} valid messages")
        return body_reference if len(body_reference) > 1 else None

    def extract(self, threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Store body reference data for threads.

        Args:
            threads: List of thread dictionaries to process

        Returns:
            List of processed body references

        Raises:
            ValueError: If threads list is empty
        """
        if not threads:
            logger.error(f"[{self.__class__.__name__}] Threads list cannot be empty")
            raise ValueError("Threads list cannot be empty")

        logger.info(f"[{self.__class__.__name__}] Starting extraction for {len(threads)} threads")
        self.references_dir.mkdir(parents=True, exist_ok=True)
        body_references = []

        for thread in threads:
            try:
                thread_id = thread.get("thread_id", "unknown")
                logger.debug(f"[{self.__class__.__name__}] Processing thread {thread_id}")

                body_reference = self._process_single_thread(thread)
                if body_reference:
                    reference_path = self.references_dir / f"{thread_id}.json"

                    with open(reference_path, "w", encoding="utf-8") as file:
                        json.dump(body_reference, file, indent=4, ensure_ascii=False)

                    ref_count = len(body_reference) - 1  # Subtract 1 for thread_id
                    logger.info(
                        f"[{self.__class__.__name__}] Stored {ref_count} body references for thread {thread_id}"
                    )
                    body_references.append(body_reference)
                else:
                    logger.debug(f"[{self.__class__.__name__}] No valid messages found in thread {thread_id}")

            except Exception as e:
                logger.error(f"[{self.__class__.__name__}] Failed to process thread {thread_id}: {e!s}", exc_info=True)
                raise

        logger.info(
            f"[{self.__class__.__name__}]  Extraction completed. Processed {len(body_references)} threads with valid content"
        )
        return body_references
