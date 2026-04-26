import io
import json
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import pdfplumber
from anthropic import AsyncAnthropic, BadRequestError

from app.schemas.transaction import TransactionCreate
from core.config import settings

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=settings.anthropic_api_key)

# Regex patterns for fallback date/amount detection
_DATE_PATTERN = re.compile(r"\b(\d{2}[-/]\d{2}[-/]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
_AMOUNT_PATTERN = re.compile(r"[\d,]+\.\d{2}")


def _normalize_date(raw: str) -> date | None:
    """Try several common date formats and return a date or None."""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            from datetime import datetime
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _extract_tabular(pdf_bytes: bytes) -> list[tuple[date, str, Decimal]] | None:
    """Try to extract transactions from a structured (tabular) PDF.

    Looks for pages that have tables with columns matching date/description/amount.
    Returns a list of (date, description, amount) tuples, or None if no tables found.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        Parsed rows or None if the PDF has no usable tables.
    """
    rows: list[tuple[date, str, Decimal]] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Normalize header row
                header = [str(cell).lower().strip() if cell else "" for cell in table[0]]

                # Find column indices
                date_col = next((i for i, h in enumerate(header) if "date" in h), None)
                desc_col = next((i for i, h in enumerate(header) if any(k in h for k in ["desc", "particular", "narration", "detail", "remark"])), None)
                amount_col = next((i for i, h in enumerate(header) if any(k in h for k in ["amount", "debit", "withdrawal", "dr"])), None)

                if date_col is None or desc_col is None or amount_col is None:
                    continue

                for data_row in table[1:]:
                    if not data_row or len(data_row) <= max(date_col, desc_col, amount_col):
                        continue

                    raw_date = str(data_row[date_col] or "").strip()
                    description = str(data_row[desc_col] or "").strip()
                    raw_amount = str(data_row[amount_col] or "").strip().replace(",", "")

                    if not raw_date or not description or not raw_amount:
                        continue

                    txn_date = _normalize_date(raw_date)
                    if txn_date is None:
                        continue

                    try:
                        amount = Decimal(raw_amount)
                        if amount == 0:
                            continue
                    except InvalidOperation:
                        continue

                    rows.append((txn_date, description, amount))

    return rows if rows else None


async def _extract_with_claude(text: str) -> list[tuple[date, str, Decimal]]:
    """Use Claude API to extract transactions from unstructured PDF text.

    Args:
        text: Raw text extracted from the PDF.

    Returns:
        List of (date, description, amount) tuples.

    Raises:
        BadRequestError: If Claude API is unavailable.
    """
    prompt = (
        "Below is text extracted from a bank statement PDF.\n"
        "Extract all individual transactions and return them as a JSON array.\n"
        "Each item must have: date (YYYY-MM-DD), description (string), amount (positive number).\n"
        "Ignore headers, footers, account summaries, opening/closing balances, and running totals.\n"
        "Only include actual debit/spend transactions — skip credits or income entries.\n"
        "Return ONLY valid JSON, no explanation.\n\n"
        f"Bank statement text:\n{text[:12000]}"
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
        raw_text = re.sub(r"\n?```$", "", raw_text)

    items: list[dict] = json.loads(raw_text)
    rows: list[tuple[date, str, Decimal]] = []
    for item in items:
        try:
            txn_date = date.fromisoformat(item["date"])
            amount = Decimal(str(item["amount"]).replace(",", ""))
            if amount == 0:
                continue
            rows.append((txn_date, str(item["description"]), amount))
        except (KeyError, ValueError, InvalidOperation):
            continue
    return rows


def _extract_with_regex(text: str) -> list[tuple[date, str, Decimal]]:
    """Last-resort regex extraction when both tabular and Claude approaches fail.

    Finds lines that contain a date and an amount, treats everything in between
    as the description. Very approximate — covers most printed statement formats.

    Args:
        text: Raw text extracted from the PDF.

    Returns:
        List of (date, description, amount) tuples (may be empty).
    """
    rows: list[tuple[date, str, Decimal]] = []
    for line in text.splitlines():
        date_match = _DATE_PATTERN.search(line)
        amount_match = _AMOUNT_PATTERN.search(line)
        if not date_match or not amount_match:
            continue
        txn_date = _normalize_date(date_match.group())
        if txn_date is None:
            continue
        try:
            amount = Decimal(amount_match.group().replace(",", ""))
            if amount == 0:
                continue
        except InvalidOperation:
            continue
        # Description = everything between date match end and amount match start
        desc_start = date_match.end()
        desc_end = amount_match.start()
        description = line[desc_start:desc_end].strip(" |-/")
        if not description:
            continue
        rows.append((txn_date, description, amount))
    return rows


async def parse_pdf(pdf_bytes: bytes) -> list[TransactionCreate]:
    """Extract transactions from a bank statement PDF.

    Tries three strategies in order:
    1. Tabular extraction via pdfplumber (fast, accurate for structured PDFs)
    2. Claude API text parsing (handles unstructured/narrative PDFs)
    3. Regex line scanning (last resort fallback)

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        List of TransactionCreate objects ready for import.

    Raises:
        ValueError: If no transactions could be extracted by any method.
    """
    # Strategy 1: tabular
    rows = _extract_tabular(pdf_bytes)
    if rows:
        logger.info("PDF parsed via tabular extraction: %d rows", len(rows))
    else:
        # Extract raw text for the other strategies
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        # Strategy 2: Claude API
        try:
            rows = await _extract_with_claude(text)
            logger.info("PDF parsed via Claude API: %d rows", len(rows))
        except (BadRequestError, Exception) as exc:
            logger.warning("Claude PDF extraction failed (%s), falling back to regex.", exc)
            rows = _extract_with_regex(text)
            logger.info("PDF parsed via regex fallback: %d rows", len(rows))

    if not rows:
        raise ValueError("No transactions could be extracted from the PDF. Check that it is a bank statement.")

    return [
        TransactionCreate(date=txn_date, description=description, amount=amount)
        for txn_date, description, amount in rows
    ]
