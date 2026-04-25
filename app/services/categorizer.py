import json
import logging

from anthropic import AsyncAnthropic, BadRequestError

from app.models.transaction import TransactionCategory
from core.config import settings

logger = logging.getLogger(__name__)

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

_KEYWORD_MAP: list[tuple[list[str], TransactionCategory]] = [
    (["zomato", "swiggy", "blinkit", "zepto", "dunzo", "bigbasket", "amazon fresh", "dmart", "reliance smart", "grocery", "food", "lunch", "dinner", "breakfast", "brunch", "restaurant", "cafe", "chai", "idli", "biryani"], TransactionCategory.FOOD),
    (["uber", "ola", "rapido", "bus", "metro", "auto", "bmtc", "irctc", "train", "flight", "makemytrip", "goibibo", "redbus", "airport", "commute", "ride"], TransactionCategory.TRANSPORT),
    (["netflix", "spotify", "amazon prime", "hotstar", "disney", "youtube premium", "apple music", "prime video", "zee5", "sonyliv", "subscription", "membership"], TransactionCategory.SUBSCRIPTIONS),
    (["electricity", "bescom", "water bill", "gas bill", "broadband", "airtel", "jio", "bsnl", "vi ", "vodafone", "recharge", "internet", "utility", "maintenance"], TransactionCategory.UTILITIES),
    (["bookmyshow", "pvr", "inox", "movie", "concert", "event", "gaming", "steam", "playstation", "xbox", "entertainment", "ipl", "standup", "comedy"], TransactionCategory.ENTERTAINMENT),
    (["sip", "mutual fund", "ppf", "nps", "fd ", "fixed deposit", "investment", "parag parikh", "zerodha", "groww", "upstox", "savings"], TransactionCategory.SAVINGS),
    (["salary", "credit", "bonus", "increment", "freelance", "payment received", "neft received", "transfer in"], TransactionCategory.SAVINGS),
    (["emi", "loan", "insurance", "lic", "hdfc life", "term plan", "health insurance", "bajaj"], TransactionCategory.UTILITIES),
    (["rent", "landlord", "housing", "pg ", "hostel"], TransactionCategory.UTILITIES),
    (["pharmacy", "medicine", "doctor", "hospital", "clinic", "pharmeasy", "netmeds", "1mg", "health"], TransactionCategory.UTILITIES),
    (["amazon", "flipkart", "myntra", "ajio", "nykaa", "shopping", "clothes", "shoes"], TransactionCategory.ENTERTAINMENT),
]


def _keyword_categorize(description: str) -> TransactionCategory:
    lower = description.lower()
    for keywords, category in _KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            return category
    return TransactionCategory.OTHER


async def categorize_transactions(descriptions: list[str]) -> list[TransactionCategory]:
    """Categorize a batch of transaction descriptions using Claude.

    Falls back to keyword-based categorization if the Claude API is unavailable
    (e.g. no credits, network error).

    Args:
        descriptions: List of transaction description strings.

    Returns:
        List of TransactionCategory values in the same order as input.
    """
    try:
        return await _categorize_with_claude(descriptions)
    except (BadRequestError, Exception) as exc:
        logger.warning("Claude categorization failed (%s), falling back to keyword matching.", exc)
        return [_keyword_categorize(d) for d in descriptions]


async def _categorize_with_claude(descriptions: list[str]) -> list[TransactionCategory]:
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
