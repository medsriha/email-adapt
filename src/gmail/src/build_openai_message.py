import json
import logging
import re
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Tuple
from urllib.parse import quote_plus

import tiktoken

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add type alias for clarity
ThreadMessage = Dict[str, Any]
ThreadList = List[Dict[str, Any]]


class OpenAIMessageBuilder:
    """Build the message for OpenAI inference."""

    PROHIBITED_SUBJECTS: ClassVar[List[str]] = ["unsubscribe", "list-unsubscribe"]

    def __init__(self, email_address: str, openai_model: str = "gpt-4o") -> None:
        """Initialize the OpenAI message builder.

        :param email_address: The email address of the user.
        :param openai_model: The OpenAI model to use for token counting.
        """
        self.email_address = email_address
        self.data_dir = self._get_data_dir()
        # Create these once during initialization
        self.references_dir, self.messages_dir = self._setup_storage_directories()
        self.openai_model = openai_model

    def _get_data_dir(self) -> Path:
        """Get the base data directory for the user."""
        safe_email = quote_plus(self.email_address)
        return Path(__file__).parent.parent.parent / "gmail/data" / safe_email

    def _get_threads_path(self) -> Path:
        """Get the path of the thread data."""
        return self.data_dir / "threads.json"

    def _get_token_count(self, text: str) -> int:
        """Get the token count of the text using OpenAI's tokenizer.

        :param text: The text to count tokens for.
        """
        try:
            # Using cl100k_base encoding which is used by gpt-4 and gpt-3.5-turbo
            encoding = tiktoken.encoding_for_model(self.openai_model)
            return len(encoding.encode(text))
        except ImportError:
            logger.warning("tiktoken not installed. Token count will be estimated.")
            # Fallback: rough estimation (1 token ≈ 4 characters)
            return len(text) // 4

    @staticmethod
    def _load_threads(data_path: Path) -> ThreadList:
        """Load thread data from JSON file.

        :param data_path: The path to the thread data on disk.
        """
        try:
            with open(data_path) as file:
                threads: ThreadList = json.load(file)
                return threads
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Error loading threads from {data_path}: {e}")
            return []

    def _setup_storage_directories(self) -> Tuple[Path, Path]:
        """Create and return necessary storage directories."""
        references_dir = self.data_dir / "references"
        messages_dir = self.data_dir / "messages"

        for dir_path in (references_dir, messages_dir):
            dir_path.mkdir(parents=True, exist_ok=True)

        return references_dir, messages_dir

    def _store_body_reference(self, threads: List[Dict[str, Any]]) -> None:
        """Store body reference data for a thread.

        Stores all valid emails from the user in the thread as references,
        skipping forwarded emails and those with prohibited subjects.

        :param threads: The list of threads to process.
        """
        for thread in threads:
            body_reference_path = self.references_dir / f"{thread['id']}.txt"

            # Initialize with thread ID
            body_reference = {"thread_id": thread["id"]}

            # Find all valid emails in thread
            for index, email in enumerate(thread.get("messages", []), 1):
                _, email_address = self._parse_from_field(email.get("from", ""))

                # Skip if not from the user
                if email_address != self.email_address:
                    continue

                # Get and clean the body
                cleaned_body = self._clean_text(email.get("body", ""))
                if not cleaned_body:
                    continue

                # Check other conditions
                subject = email.get("subject", "").lower()
                is_forwarded = email.get("is_forwarded", False)

                if (
                    not any(prohibited_subject in subject for prohibited_subject in self.PROHIBITED_SUBJECTS)
                    and not is_forwarded
                ):
                    body_reference[f"body_reference_{index}"] = {
                        "content": cleaned_body,
                        "cost": self._get_token_count(cleaned_body),
                    }

            # Save if we found any valid references
            if len(body_reference) > 1:  # More than just thread_id
                try:
                    with open(body_reference_path, "w", encoding="utf-8") as file:
                        json.dump(body_reference, file, indent=4, ensure_ascii=False)
                    logger.debug(f"Stored body reference for thread {thread['id']} at {body_reference_path}")
                except Exception as e:
                    logger.error(f"Failed to store body reference for thread {thread['id']}: {e}")

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean up the text by removing URLs and extra newlines.

        :param text: The text to clean.
        """
        # URL regex pattern that matches http, https, and www URLs
        url_pattern = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|www\.[a-zA-Z0-9][a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+(?:/[^\s]*)?"

        # Replace all URLs with <URL>
        cleaned_text = re.sub(url_pattern, "<URL>", text)

        # Remove any leading or trailing whitespace
        cleaned_text = cleaned_text.strip()
        # Remove any leading or trailing newlines
        cleaned_text = cleaned_text.strip("\n")
        # Replace any sequence of 3 or more newlines with exactly 2 newlines
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

        return cleaned_text

    def _build_message(self, threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Construct the message for OpenAI inference."""
        messages = []
        for index, thread in enumerate(threads, 1):
            thread_messages = [{"role": "system", "content": "You are a professional email assistant."}]

            for counter, email in enumerate(thread.get("messages", [])):
                _, email_address = self._parse_from_field(email.get("from", ""))
                is_assistant = email_address == self.email_address

                cleaned_body = self._clean_text(email.get("body", ""))

                # Add subject as first user message
                if len(thread_messages) == 1:
                    thread_messages.append({"role": "user", "content": f"Subject: {email.get('subject', '')}"})

                content = {
                    "role": "assistant" if is_assistant else "user",
                    "content": f"""Email {counter + 1}:\n\nFrom: {email.get('from', '')}\nTo: {email.get('to', '')}\n
Date:{email.get('date', '')}\n
Body: {cleaned_body}""",
                }
                thread_messages.append(content)

            if len(thread_messages) > 1:
                result = {"id": thread.get("id", ""), "thread": thread_messages}
                messages.append(result)

                # Save thread messages
                messages_path = self.messages_dir / f"messages-{index}.json"
                with open(messages_path, "w", encoding="utf-8") as file:
                    json.dump(result, file, indent=4, ensure_ascii=False)

        return messages

    @staticmethod
    def _parse_from_field(from_string: str) -> Tuple[str, str]:
        """Parse the 'from' field to separate name and email address.

        :param from_string: String containing name and email (e.g. "John Doe <john@example.com>").
        """
        # Handle empty or invalid input
        if not from_string:
            return "", ""

        # Try to match pattern "Name <email@domain.com>"
        match = re.match(r"^(.*?)\s*<(.+?)>$", from_string)

        if match:
            name = match.group(1).strip()
            email = match.group(2).strip()
        else:
            # If no match, treat entire string as email
            name = ""
            email = from_string.strip()

        return name, email

    def build_message(self) -> ThreadList:
        """Build the message for OpenAI inference."""
        threads_path = self._get_threads_path()
        threads = self._load_threads(threads_path)
        messages = self._build_message(threads)

        self._store_body_reference(threads)

        return messages
