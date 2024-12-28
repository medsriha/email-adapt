import re
from typing import Pattern

EMAIL_REGEX: Pattern[str] = re.compile(r"^[a-zA-Z0-9._%+-]+@gmail.com$")


def validate_gmail_email(email_address: str) -> None:
    """Validate email format.

    :param email_address: Email address to validate.
    """
    if not isinstance(email_address, str):
        raise TypeError("Email must be a string")
    if not email_address or not email_address.strip():
        raise ValueError("Email cannot be empty")
    if not EMAIL_REGEX.match(email_address):
        raise ValueError(f"Invalid GMAIL email format: {email_address}")
