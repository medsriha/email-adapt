import base64
import json
import logging
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Union
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class GmailThreadExtractor:
    """A class to handle Gmail thread extraction."""

    SCOPES: ClassVar[List[str]] = ["https://www.googleapis.com/auth/gmail.readonly"]
    MAX_RETRIES: ClassVar[int] = 3
    MIME_TYPE_PLAIN = "text/plain"
    MIME_TYPE_HTML = "text/html"

    def __init__(self, email_address: str) -> None:
        """Initialize the extractor with email and optional root directory."""
        self.email_address = email_address
        self.root_dir = Path(__file__).parent.parent.parent
        self._setup_paths()
        self.creds = self._get_credentials()
        self.service = self._initialize_service()

    def _setup_paths(self) -> None:
        """Set up necessary paths and directories."""
        safe_email = quote_plus(self.email_address)

        # Define all paths
        self.credentials_path = self.root_dir / "gmail/credentials/credentials.json"
        self.credentials_user_dir = self.root_dir / "gmail/credentials" / safe_email
        self.data_user_dir = self.root_dir / "gmail/data" / safe_email
        self.token_path = self.credentials_user_dir / "token.json"
        self.data_path = self.data_user_dir / "threads.json"

        if not self.credentials_path.exists():
            raise FileNotFoundError(f"Credentials file not found at {self.credentials_path}")

        # Create directories
        for directory in (self.credentials_user_dir, self.data_user_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created/verified directory at: {directory}")
            except Exception as e:
                logger.error(f"Failed to create directory {directory}: {e}")
                raise

    def _initialize_service(self) -> Resource:
        """Initialize the Gmail API service with retry logic."""
        for attempt in range(self.MAX_RETRIES):
            try:
                return build("gmail", "v1", credentials=self.creds)
            except HttpError as e:
                if attempt == self.MAX_RETRIES - 1:
                    logger.error(f"Failed to initialize Gmail service after {self.MAX_RETRIES} attempts")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error initializing Gmail service: {e}")
                raise

    def _get_credentials(self) -> Optional[Credentials]:
        """Get and refresh OAuth 2.0 credentials."""
        creds: Optional[Credentials] = None

        # Try to load existing token
        try:
            creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)  # type: ignore[no-untyped-call]
        except Exception:
            logger.warning("Failed to load existing token")
            pass

        # If credentials are expired or don't exist, refresh or create new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())  # type: ignore[no-untyped-call]
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.SCOPES)
                creds = flow.run_local_server(port=0)
            if creds:
                # Save the credentials for future use
                with open(self.token_path, "w") as token:
                    token.write(creds.to_json())  # type: ignore[no-untyped-call]
            else:
                logger.error("Failed to retrieve and update user's token")
                return None

        return creds

    def _extract_text_from_html(self, html_content: str) -> str:
        """Extract readable text from HTML content.

        :param html_content: HTML string to parse.
        """
        text: str = html_content

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            # Handle common email formatting
            for br in soup.find_all("br"):
                br.replace_with("\n")
            for p in soup.find_all("p"):
                p.append("\n")

            # Get text and clean up whitespace
            text = soup.get_text()
            if text:
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = "\n".join(chunk for chunk in chunks if chunk)

            return text
        except Exception as e:
            logger.warning(f"Failed to parse HTML content: {e}")
            return html_content

    def _get_message_body(self, payload: Dict[str, Any]) -> str:
        """Extract the message body from the payload recursively."""
        if "body" in payload and "data" in payload["body"]:
            content = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            return self._extract_text_from_html(content) if payload.get("mimeType") == self.MIME_TYPE_HTML else content

        if "parts" not in payload:
            return ""

        # Process parts in order of preference
        for mime_type in (self.MIME_TYPE_PLAIN, self.MIME_TYPE_HTML):
            for part in payload["parts"]:
                if part["mimeType"] == mime_type and "data" in part.get("body", {}):
                    content = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                    return self._extract_text_from_html(content) if mime_type == self.MIME_TYPE_HTML else content

        # If no suitable part found, recurse into first part
        return self._get_message_body(payload["parts"][0]) if payload["parts"] else ""

    def get_threads(self, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch Gmail threads matching the specified query and return them."""
        try:
            results = (
                self.service.users()
                .threads()
                .list(userId="me", maxResults=max_results, q=f"from:{self.email_address} in:anywhere")
                .execute()
            )
            threads = results.get("threads", [])

            detailed_threads = [
                {
                    "thread_id": thread_data["id"],
                    "messages": [self._parse_message(msg) for msg in thread_data["messages"]],
                    "messageCount": len(thread_data["messages"]),
                }
                for thread_data in (
                    self.service.users().threads().get(userId="me", id=thread["id"]).execute() for thread in threads
                )
            ]

            # Save to file
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(detailed_threads, f, indent=4, ensure_ascii=False)
            logger.info(f"Saved {len(detailed_threads)} threads to {self.data_path}")

            return detailed_threads

        except Exception as e:
            logger.error(f"Error fetching threads: {e}")
            raise

    def _parse_message(self, message: Dict[str, Any]) -> Dict[str, Union[str, bool]]:
        """Parse a message within a thread.

        :param message: Gmail message to parse.
        """
        headers = message["payload"]["headers"]
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")

        # Check if message is forwarded by looking at subject and headers
        is_forwarded = any(
            [
                subject.lower().startswith("fwd:"),
                subject.lower().startswith("fw:"),
                any(h["name"].lower() == "x-forwarded-for" for h in headers),
                any(h["name"].lower() == "x-forwarded-from" for h in headers),
            ]
        )

        return {
            "message_id": message["id"],
            "subject": subject,
            "from": next((h["value"] for h in headers if h["name"].lower() == "from"), ""),
            "to": next((h["value"] for h in headers if h["name"].lower() == "to"), ""),
            "date": next((h["value"] for h in headers if h["name"].lower() == "date"), ""),
            "body": self._get_message_body(message["payload"]),
            "labelIds": message.get("labelIds", []),
            "is_forwarded": is_forwarded,
        }
