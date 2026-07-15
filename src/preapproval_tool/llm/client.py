"""Thin wrapper around the OpenAI API for schema-validated structured calls.

Every LLM call in this system goes through `structured_completion`: the caller
supplies a JSON Schema, and the response is validated against it before it is
trusted anywhere downstream (extraction, categorization fallback, criterion
judgment, chat-intent parsing). On a schema violation we retry once with the
validation error fed back to the model; if that also fails we raise LLMError
rather than silently passing through unvalidated data.

No page/document content is ever treated as instructions — callers must always
pass untrusted text (PDF text, fetched web content) as clearly delimited data
inside the user prompt, never concatenated into the system prompt.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from jsonschema import Draft7Validator
from openai import OpenAI

load_dotenv()


class LLMError(RuntimeError):
    """Raised when the model fails to produce schema-valid structured output."""


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-replace-me"):
        raise LLMError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add a real key."
        )
    return OpenAI(api_key=api_key)


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o")


def structured_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    schema_name: str,
    max_repair_attempts: int = 1,
) -> dict[str, Any]:
    """Call the model and return output validated against json_schema.

    Uses OpenAI Structured Outputs (response_format=json_schema, strict) as the
    first line of defense, then independently re-validates with jsonschema
    before returning — belt and suspenders, since strict mode covers most but
    not all JSON Schema constructs (e.g. numeric bounds).
    """
    validator = Draft7Validator(json_schema)
    client = _client()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    attempt = 0
    last_error: str | None = None
    while attempt <= max_repair_attempts:
        if last_error:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response did not match the required JSON "
                        f"schema. Validation error: {last_error}\n"
                        "Return ONLY corrected JSON matching the schema."
                    ),
                }
            )
        response = client.chat.completions.create(
            model=_model(),
            messages=messages,  # type: ignore[arg-type]
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
        )
        raw = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_error = f"invalid JSON: {exc}"
            attempt += 1
            continue

        errors = sorted(validator.iter_errors(parsed), key=lambda e: e.path)
        if not errors:
            return parsed
        last_error = "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
        attempt += 1

    raise LLMError(
        f"Model failed to produce schema-valid output for '{schema_name}' after "
        f"{max_repair_attempts + 1} attempts. Last error: {last_error}"
    )
