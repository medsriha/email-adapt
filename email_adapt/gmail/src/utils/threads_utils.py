import re
from typing import Tuple


def clean_text(text: str) -> str:
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

    return cleaned_text


def parse_from_field(from_string: str) -> Tuple[str, str]:
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
