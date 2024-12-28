import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Pattern, Union
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
    EMAIL_REGEX: ClassVar[Pattern[str]] = re.compile(r"^[a-zA-Z0-9._%+-]+@gmail.com$")

    def _validate_email(self, email_address: str) -> None:
        """Validate email format.

        :param email_address: Email address to validate.
        """
        if not isinstance(email_address, str):
            raise TypeError("Email must be a string")
        if not email_address or not email_address.strip():
            raise ValueError("Email cannot be empty")
        if not self.EMAIL_REGEX.match(email_address):
            raise ValueError(f"Invalid GMAIL email format: {email_address}")

    def _setup_paths(self, root_dir: Path, user_email: str) -> None:
        """Set up necessary paths and directories.

        :param root_dir: Project root directory.

        """
        # Set up credentials path
        self.credentials_path = root_dir / "gmail/credentials/credentials.json"
        if not self.credentials_path.exists():
            raise FileNotFoundError("Credentials file not found")

        # Create user directory with URL-safe email as folder name
        safe_email = quote_plus(user_email)
        credentials_user_dir = root_dir / "gmail/credentials" / safe_email
        data_user_dir = root_dir / "gmail/data" / safe_email

        try:
            credentials_user_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created/verified user directory at: {credentials_user_dir}")
        except Exception as e:
            logger.error(f"Failed to create user directory: {e}")
            raise

        try:
            data_user_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created/verified user directory at: {data_user_dir}")
        except Exception as e:
            logger.error(f"Failed to create user directory: {e}")
            raise

        # Set up token path
        self.token_path = credentials_user_dir / "token.json"
        self.data_path = data_user_dir / "threads.json"

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
            logger.error("Failed to load existing token")
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
        """Extract the message body from the payload.

        :param payload: Gmail message payload.
        """
        if "parts" in payload:
            # Try to find plain text first
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    if "data" in part["body"]:
                        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                    return ""

            # If no plain text, try HTML
            for part in payload["parts"]:
                if part["mimeType"] == "text/html":
                    if "data" in part["body"]:
                        html_content = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        return self._extract_text_from_html(html_content)
                    return ""

            # If neither found, recurse into first part
            return self._get_message_body(payload["parts"][0])

        if "body" in payload and "data" in payload["body"]:
            content = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            if payload.get("mimeType") == "text/html":
                return self._extract_text_from_html(content)
            return content

        return ""

    def get_threads(self, user_email: str, max_results: Optional[int] = None) -> None:
        """Fetch and save Gmail threads matching the specified query.

        :param user_email: user email address.
        :param max_results: Maximum number of threads to return.
        """
        # Validate email
        self._validate_email(user_email)

        # Get the project root directory (where pyproject.toml is located)
        root_dir = Path(__file__).parent.parent.parent

        # Set up paths
        self._setup_paths(root_dir=root_dir, user_email=user_email)

        # Initialize API client
        self.creds = self._get_credentials()
        self.service = self._initialize_service()

        try:
            results = (
                self.service.users()
                .threads()
                .list(userId="me", maxResults=max_results, q=f"from:{user_email} in:anywhere")
                .execute()
            )

            threads = results.get("threads", [])

            detailed_threads = []
            for thread in threads:
                thread_data = self.service.users().threads().get(userId="me", id=thread["id"]).execute()

                detailed_threads.append(
                    {
                        "id": thread_data["id"],
                        "messages": [self._parse_message(msg) for msg in thread_data["messages"]],
                        "messageCount": len(thread_data["messages"]),
                    }
                )

            with open(self.data_path, "w") as f:
                json.dump(detailed_threads, f, indent=4, ensure_ascii=False)
            logger.info(f"Saved {len(detailed_threads)} threads to threads.json")

        except Exception as e:
            logger.error(f"Error fetching threads: {e!s}")

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
            "id": message["id"],
            "subject": subject,
            "from": next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown"),
            "date": next((h["value"] for h in headers if h["name"].lower() == "date"), ""),
            "body": self._get_message_body(message["payload"]),
            "labelIds": message.get("labelIds", []),
            "is_forwarded": is_forwarded,
        }
