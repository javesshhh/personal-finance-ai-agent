import uuid
from collections.abc import Callable
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.services import session_service, transaction_service
from app.services.pdf_parser import parse_pdf
from core.database import AsyncSessionLocal


def register_transaction_tools(mcp: FastMCP, get_session_id: Callable[[], uuid.UUID]) -> None:

    async def _resolve_session(session_name: str) -> uuid.UUID:
        """Return session_id for the given name, or the default if name is empty."""
        if not session_name.strip():
            return get_session_id()
        async with AsyncSessionLocal() as db:
            session = await session_service.get_or_create_by_name(db, session_name.strip())
            return session.id

    @mcp.tool()
    async def list_sessions() -> str:
        """List all available sessions. Call this before importing files or when the user
        wants to know what data sources / accounts are available."""
        async with AsyncSessionLocal() as db:
            sessions = await session_service.list_sessions(db)
        if not sessions:
            return "No sessions found. Use import_file to create one."
        lines = [f"- {s.name} (id: {s.id})" for s in sessions]
        return "Available sessions:\n" + "\n".join(lines)

    @mcp.tool()
    async def import_file(file_path: str, session_name: str) -> str:
        """Import a bank statement file (CSV or PDF) into a named session.

        Creates the session automatically if it does not exist yet.
        Skips duplicate transactions so the same file can be safely re-imported.

        Args:
            file_path: Absolute path to the CSV or PDF file on the user's machine.
            session_name: Name of the session to import into (e.g. "hdfc credit card").
                          A new session is created if the name doesn't exist yet.
        """
        path = Path(file_path.strip())
        if not path.exists():
            return f"File not found: {file_path}"

        suffix = path.suffix.lower()
        if suffix not in {".csv", ".pdf"}:
            return f"Unsupported file type '{suffix}'. Only .csv and .pdf are supported."

        raw = path.read_bytes()
        sid = await _resolve_session(session_name)

        async with AsyncSessionLocal() as db:
            if suffix == ".csv":
                result = await transaction_service.import_csv(db, sid, raw)
            else:
                try:
                    parsed_rows = await parse_pdf(raw)
                except ValueError as exc:
                    return f"Could not extract transactions from PDF: {exc}"
                rows = [(r.date, r.description, r.amount) for r in parsed_rows]
                result = await transaction_service.import_rows(db, sid, rows)

        return (
            f"Imported {result.imported} transactions into '{session_name}'. "
            f"Skipped {result.skipped_duplicates} duplicates."
        )

    @mcp.tool()
    async def get_spending(start_date: str, end_date: str, session_name: str = "") -> str:
        """Get spending totals by category between two dates.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
            session_name: Which session to query (e.g. "hdfc credit card").
                          Leave empty to use the default session.
        """
        sid = await _resolve_session(session_name)
        async with AsyncSessionLocal() as db:
            results = await transaction_service.get_spending_by_category(
                db,
                sid,
                date.fromisoformat(start_date),
                date.fromisoformat(end_date),
            )
        label = f" [{session_name}]" if session_name.strip() else ""
        if not results:
            return f"No spending data found{label} for that date range."
        lines = [f"{r.category.value}: ₹{r.total:,.2f} ({r.count} transactions)" for r in results]
        return f"Spending{label}:\n" + "\n".join(lines)

    @mcp.tool()
    async def compare_months(
        year_a: int, month_a: int, year_b: int, month_b: int, session_name: str = ""
    ) -> str:
        """Compare spending by category between two calendar months.

        Args:
            year_a: Year of the first month (e.g. 2025).
            month_a: Month number of the first month (1-12).
            year_b: Year of the second month.
            month_b: Month number of the second month (1-12).
            session_name: Which session to query (e.g. "hdfc credit card").
                          Leave empty to use the default session.
        """
        sid = await _resolve_session(session_name)
        async with AsyncSessionLocal() as db:
            results = await transaction_service.compare_months(db, sid, year_a, month_a, year_b, month_b)
        label = f" [{session_name}]" if session_name.strip() else ""
        if not results:
            return f"No data found{label} for the requested months."
        lines = [
            f"{r.category.value}: ₹{r.month_a_total:,.2f} → ₹{r.month_b_total:,.2f} "
            f"({'↑' if r.delta > 0 else '↓'} {abs(r.delta_pct):.1f}%)"
            for r in results
        ]
        return f"Month comparison{label}:\n" + "\n".join(lines)
