import json
from pathlib import Path
from typing import Optional

import yaml
from openai import OpenAI

from email_adapt.database.vector_store import VectorStore


class UserProfile:
    def __init__(self, vector_store: VectorStore):
        """Initialize UserProfile with an existing VectorStore instance.

        :param vector_store: An initialized VectorStore instance
        """
        self.vector_store = vector_store

        # Initialize OpenAI client
        self.client = OpenAI()
        # Load the prompt template from YAML
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "user_profile.yaml"

        with open(prompt_path) as f:
            self.prompt_template = yaml.safe_load(f)["prompt"]["template"]

    def _get_emails(
        self,
        metadata_filter: Optional[dict] = {"is_forwarded": False},
        top_k: int = 10,
        weight_recency: float = 1.0,
        weight_length: float = 1.0,
    ):
        """Get emails from the database
        """
        all_emails = self.vector_store.search(
            top_k=top_k, weight_recency=weight_recency, weight_length=weight_length, metadata_filter=metadata_filter
        )

        # Sanitize and join emails with counters
        sanitized_emails = []
        for i, email in enumerate(all_emails):
            # Ensure text is a string and remove null bytes
            text = str(email.get("text", "")).replace("\x00", "")

            # Remove excessive whitespace and normalize line endings
            text = " ".join(text.split())

            # Skip empty emails
            if not text.strip():
                continue

            # Format with counter
            sanitized_emails.append(f"Email {i+1}:\n{text}\n")

        # Join all sanitized emails with double newlines for better readability
        texts = "\n\n".join(sanitized_emails)

        if not texts.strip():
            raise ValueError("No valid email content found after sanitization")

        return texts

    def create_user_profile(
        self,
        metadata_filter: Optional[dict],
        top_k: Optional[int],
        weight_recency: Optional[float],
        weight_length: Optional[float],
        model: str = "gpt-4o",
    ) -> dict:
        """Create a user profile by analyzing emails using the specified LLM model.

        Args:
            model (str): The OpenAI model to use for analysis

        Returns:
            dict: The extracted user profile information
        """
        emails = self._get_emails(
            metadata_filter=metadata_filter, top_k=top_k, weight_recency=weight_recency, weight_length=weight_length
        )

        # Format the prompt with the email texts
        prompt = self.prompt_template.format(emails=emails)

        try:
            # Make the API request
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert at extracting user information from emails."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=4096,
                model=model,
            )
        except Exception as e:
            print(f"Error creating user profile: {e}")
            raise

        # Parse the JSON response
        try:
            return response.choices[0].message.content
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")
