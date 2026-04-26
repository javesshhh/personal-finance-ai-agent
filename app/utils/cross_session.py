import re

# Keywords that indicate a payment/transfer TO another account rather than a purchase
_PAYMENT_KEYWORDS: tuple[str, ...] = (
    "bill payment",
    "bill pay",
    "credit card bill",
    "cc bill",
    "card payment",
    "card bill",
    "emi payment",
    "loan emi",
    "loan payment",
    "transfer to",
    "neft to",
    "imps to",
    "upi to",
    "payment",
    "bill",
)

# Words too common to count as meaningful session-name overlap
_STOPWORDS = frozenset({"to", "a", "an", "the", "and", "for", "of", "in", "on", "at", "by", "my"})


def _meaningful_words(text: str) -> set[str]:
    """Return lowercased meaningful tokens from text, filtering stopwords and short words.

    Args:
        text: Any string (session name or transaction description).

    Returns:
        Set of words with length > 2 that are not in the stopword list.
    """
    tokens = re.sub(r"[^a-z0-9 ]", "", text.lower()).split()
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def is_payment_toward_session(description: str, session_name: str) -> bool:
    """Return True if a transaction description looks like a payment to a named session.

    Uses two independent signals:
    1. Word overlap — at least one meaningful word from ``session_name`` appears in
       ``description`` (e.g., "hdfc" appears in both "HDFC Credit Card Bill" and
       the session name "hdfc credit card").
    2. Payment keyword — the description contains a term that indicates a
       payment/transfer context (e.g., "bill", "payment", "EMI").

    Both signals must be present for a positive match.

    Args:
        description: Transaction description text to analyse.
        session_name: Name of a different session to check against.

    Returns:
        True if this transaction is likely a payment toward that session's account.
    """
    desc_words = _meaningful_words(description)
    session_words = _meaningful_words(session_name)

    if not (desc_words & session_words):
        return False

    desc_lower = description.lower()
    return any(kw in desc_lower for kw in _PAYMENT_KEYWORDS)


def find_inter_session_transfer_ids(
    transactions: list,
    session_id_to_name: dict,
) -> frozenset[int]:
    """Return transaction IDs that are likely payments from one session to another.

    Used to prevent double-counting when aggregating spending across all sessions.
    For example: "HDFC Credit Card Bill ₹15,000" in a savings session should be
    excluded if the individual card transactions are already tracked in an HDFC session.

    A transaction is flagged when:
    - Its description word-overlaps with another session's name
    - AND its description contains a payment/bill/transfer keyword

    Args:
        transactions: List of Transaction ORM instances (must have .id, .session_id, .description).
        session_id_to_name: Mapping of session UUID → session name for all known sessions.

    Returns:
        Frozenset of transaction IDs to exclude from cross-session aggregation.
    """
    exclude_ids: set[int] = set()
    all_session_names = list(session_id_to_name.values())

    for txn in transactions:
        own_name = session_id_to_name.get(txn.session_id, "")
        for target_name in all_session_names:
            if target_name == own_name:
                continue
            if is_payment_toward_session(txn.description, target_name):
                exclude_ids.add(txn.id)
                break

    return frozenset(exclude_ids)
