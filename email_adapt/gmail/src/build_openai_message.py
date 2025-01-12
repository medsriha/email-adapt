import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

from email_adapt.gmail.src.utils.threads_utils import clean_text, parse_from_field

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ThreadList = List[Dict[str, Any]]


class OpenAIMessageBuilder:
    """Build messages for OpenAI inference from email threads."""

    def __init__(self, email_address: str) -> None:
        self.email_address = email_address
        logger.info(f"[{self.__class__.__name__}] Initializing OpenAIMessageBuilder for email: {email_address}")
        self.messages_dir = self._setup_messages_directory()

    def _setup_messages_directory(self) -> Path:
        """Create and return the messages directory path."""
        messages_dir = Path(__file__).parent.parent.parent / "data" / quote_plus(self.email_address) / "messages"
        messages_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"[{self.__class__.__name__}] Created messages directory at: {messages_dir}")
        return messages_dir

    def _create_email_content(self, email: Dict[str, Any], counter: int) -> Dict[str, Any]:
        """Format a single email message for OpenAI."""
        _, sender_email = parse_from_field(email.get("from", ""))
        is_assistant = sender_email == self.email_address

        email_text = (
            f"Email {counter}:\n\n"
            f"From: {email.get('from', '')}\n"
            f"To: {email.get('to', '')}\n"
            f"Date: {email.get('date', '')}\n\n"
            f"Body: {clean_text(email.get('body', ''))}"
        )

        return {"role": "assistant" if is_assistant else "user", "content": [{"type": "text", "text": email_text}]}

    def _process_thread(self, thread: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single email thread."""
        thread_id = thread["thread_id"]
        logger.debug(f"[{self.__class__.__name__}] Processing thread ID: {thread_id}")

        messages = [{"role": "system", "content": "You are a professional email assistant."}]

        # Add subject as first user message
        if thread.get("messages", []):
            subject = thread["messages"][0].get("subject", "")
            logger.debug(f"[{self.__class__.__name__}] Thread {thread_id} subject: {subject}")
            messages.append({"role": "user", "content": [{"type": "text", "text": f"Subject: {subject}"}]})

        # Process each email in the thread
        for counter, email in enumerate(thread.get("messages", []), 1):
            messages.append(self._create_email_content(email, counter))

        logger.debug(
            f"[{self.__class__.__name__}] Processed {len(thread.get('messages', []))} emails in thread {thread_id}"
        )
        return {"thread_id": thread_id, "messages": messages}

    def build_message(self, threads: ThreadList) -> ThreadList:
        """Build and save OpenAI messages for all threads."""
        logger.info(f"[{self.__class__.__name__}] Processing {len(threads)} threads")
        processed_threads = []

        for thread in threads:
            if not thread.get("messages", []):
                logger.warning(f"[{self.__class__.__name__}] Skipping empty thread: {thread.get('thread_id')}")
                continue

            thread_data = self._process_thread(thread)
            processed_threads.append(thread_data)

            # Save thread messages to file
            messages_path = self.messages_dir / f"{thread['thread_id']}.json"
            try:
                with open(messages_path, "w", encoding="utf-8") as file:
                    json.dump(thread_data, file, indent=4, ensure_ascii=False)
                logger.debug(f"[{self.__class__.__name__}] Saved thread {thread['thread_id']} to {messages_path}")
            except OSError as e:
                logger.error(f"[{self.__class__.__name__}] Failed to save thread {thread['thread_id']}: {e!s}")

        logger.info(f"[{self.__class__.__name__}] Successfully processed {len(processed_threads)} threads")
        return processed_threads
