import json

from anthropic import AsyncAnthropic

from app.models.transaction import TransactionCategory
from core.config import settings

client = AsyncAnthropic(api_key=settings.anthropic_api_key)

CATEGORY_LIST = ", ".join([c.value for c in TransactionCategory])

SYSTEM_PROMPT = f"""You are a financial transaction categorizer.
Given a JSON array of bank transaction descriptions, assign each one a category from this list:
{CATEGORY_LIST}

Rules:
- Respond ONLY with a valid JSON array of category strings, one per transaction, in the same order.
- Use "other" if no category fits clearly.
- Example input: ["Swiggy order", "Uber ride", "Netflix"]
- Example output: ["food", "transport", "subscriptions"]
"""

CHUNK_SIZE = 50


async def categorize_transactions(descriptions: list[str]) -> list[TransactionCategory]:
    """Categorize a batch of transaction descriptions using Claude.

    Sends descriptions in chunks of 50 to stay within token limits.
    Falls back to OTHER for any category Claude returns that is unrecognised.

    Args:
        descriptions: List of transaction description strings.

    Returns:
        List of TransactionCategory values in the same order as input.
    """
    results: list[TransactionCategory] = []

    for i in range(0, len(descriptions), CHUNK_SIZE):
        chunk = descriptions[i : i + CHUNK_SIZE]

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(chunk)}],
        )

        raw: list[str] = json.loads(response.content[0].text.strip())
        results.extend([TransactionCategory.coerce(c) for c in raw])

    return results
