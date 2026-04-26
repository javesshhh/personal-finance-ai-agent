"""Generate dummy HDFC credit card statement PDFs for January and February 2025."""

from fpdf import FPDF

JANUARY = [
    ("01 Jan 2025", "Swiggy Order - Koramangala",        "648.00"),
    ("02 Jan 2025", "Uber India - Trip fare",             "185.00"),
    ("03 Jan 2025", "Netflix India Pvt Ltd",              "649.00"),
    ("05 Jan 2025", "Amazon India - Electronics",         "2499.00"),
    ("06 Jan 2025", "Zomato Ltd",                         "420.00"),
    ("08 Jan 2025", "BookMyShow - Movie Tickets",         "700.00"),
    ("09 Jan 2025", "Reliance Smart - Groceries",         "1850.00"),
    ("10 Jan 2025", "Ola Cabs - Trip",                    "220.00"),
    ("11 Jan 2025", "Spotify India",                      "119.00"),
    ("13 Jan 2025", "Swiggy Instamart",                   "760.00"),
    ("14 Jan 2025", "Airtel Prepaid Recharge",            "299.00"),
    ("15 Jan 2025", "Zomato - Weekend Brunch",            "890.00"),
    ("17 Jan 2025", "Rapido Technologies",                "80.00"),
    ("18 Jan 2025", "BigBasket Grocery",                  "2340.00"),
    ("20 Jan 2025", "Amazon Prime Membership",            "1499.00"),
    ("21 Jan 2025", "Uber India - Late Night",            "350.00"),
    ("22 Jan 2025", "Zomato - Dinner",                    "540.00"),
    ("24 Jan 2025", "DMart - Weekly Shopping",            "3200.00"),
    ("25 Jan 2025", "Swiggy - Lunch",                     "380.00"),
    ("27 Jan 2025", "BookMyShow - Event",                 "1200.00"),
    ("28 Jan 2025", "Blinkit - Quick Commerce",           "910.00"),
    ("29 Jan 2025", "Ola Cabs - Airport",                 "680.00"),
    ("30 Jan 2025", "Zomato - Late Night Order",          "320.00"),
    ("31 Jan 2025", "Myntra - Clothing",                  "1799.00"),
]

FEBRUARY = [
    ("01 Feb 2025", "Swiggy Order - Sunday Brunch",      "720.00"),
    ("02 Feb 2025", "Uber India - Office Commute",        "195.00"),
    ("03 Feb 2025", "BigBasket Weekly Order",             "1980.00"),
    ("04 Feb 2025", "Zomato - Valentine Dinner",          "2800.00"),
    ("05 Feb 2025", "PharmEasy - Medicine",               "640.00"),
    ("06 Feb 2025", "Rapido - Bike Ride",                 "95.00"),
    ("07 Feb 2025", "Airtel Broadband Bill",              "999.00"),
    ("08 Feb 2025", "Netflix India Pvt Ltd",              "649.00"),
    ("09 Feb 2025", "Ola Cabs",                           "240.00"),
    ("10 Feb 2025", "Zomato - Lunch",                     "380.00"),
    ("11 Feb 2025", "Amazon Fresh - Groceries",           "1150.00"),
    ("12 Feb 2025", "Uber India - Late Night",            "350.00"),
    ("13 Feb 2025", "Swiggy Instamart",                   "580.00"),
    ("14 Feb 2025", "Zomato - Valentine Special",         "3200.00"),
    ("15 Feb 2025", "BookMyShow - Standup Show",          "1200.00"),
    ("16 Feb 2025", "Spotify India",                      "119.00"),
    ("17 Feb 2025", "Rapido - Bike Ride",                 "75.00"),
    ("18 Feb 2025", "DMart Monthly Shopping",             "2800.00"),
    ("19 Feb 2025", "Swiggy - Office Lunch",              "410.00"),
    ("21 Feb 2025", "Zomato - Dinner",                    "560.00"),
    ("22 Feb 2025", "Uber India - Airport Pickup",        "720.00"),
    ("23 Feb 2025", "Amazon India - Books",               "899.00"),
    ("24 Feb 2025", "Swiggy - Lunch",                     "395.00"),
    ("25 Feb 2025", "Zepto Instant Delivery",             "510.00"),
    ("26 Feb 2025", "MakeMyTrip - Goa Flights",           "8500.00"),
    ("27 Feb 2025", "Zomato - Office Order",              "290.00"),
    ("28 Feb 2025", "Gym Membership - Cult.fit",          "1500.00"),
]


def build_pdf(month_label: str, statement_date: str, due_date: str, transactions: list) -> FPDF:
    pdf = FPDF()
    pdf.add_page()

    # ── Header bar ──────────────────────────────────────────────────────────
    pdf.set_fill_color(0, 56, 120)       # HDFC dark blue
    pdf.rect(0, 0, 210, 28, style="F")

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 7)
    pdf.cell(0, 10, "HDFC Bank Credit Card Statement", ln=True)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(10, 18)
    pdf.cell(0, 6, "HDFC Bank Ltd  |  Credit Cards Division  |  PO Box 8654, Thiruvananthapuram - 695 014")

    # ── Account summary box ──────────────────────────────────────────────────
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(10, 35)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(235, 242, 255)
    pdf.cell(190, 7, "Account Summary", ln=True, fill=True)

    pdf.set_font("Helvetica", "", 9)
    total = sum(float(t[2].replace(",", "")) for t in transactions)

    summary = [
        ("Statement Period", month_label),
        ("Statement Date",   statement_date),
        ("Payment Due Date", due_date),
        ("Total Amount Due", f"Rs. {total:,.2f}"),
        ("Minimum Amount Due", f"Rs. {total * 0.05:,.2f}"),
        ("Credit Limit", "Rs. 3,00,000.00"),
        ("Available Credit Limit", f"Rs. {300000 - total:,.2f}"),
    ]

    col_w = 95
    for label, value in summary:
        x = pdf.get_x()
        y = pdf.get_y()
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_w, 6, label, border=0)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_w, 6, value, border=0, ln=True)

    # ── Transaction table header ─────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_fill_color(0, 56, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)

    col_date  = 32
    col_desc  = 118
    col_amt   = 40

    pdf.cell(col_date, 7, "Date",        border=1, fill=True, align="C")
    pdf.cell(col_desc, 7, "Description", border=1, fill=True, align="C")
    pdf.cell(col_amt,  7, "Amount (Rs)", border=1, fill=True, align="C", ln=True)

    # ── Transaction rows ─────────────────────────────────────────────────────
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)

    for i, (txn_date, description, amount) in enumerate(transactions):
        fill = i % 2 == 0
        pdf.set_fill_color(245, 248, 255) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.cell(col_date, 6, txn_date,     border=1, fill=fill, align="C")
        pdf.cell(col_desc, 6, description,  border=1, fill=fill)
        pdf.cell(col_amt,  6, amount,        border=1, fill=fill, align="R", ln=True)

    # ── Totals row ───────────────────────────────────────────────────────────
    pdf.set_fill_color(220, 230, 245)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_date + col_desc, 7, "Total Charges", border=1, fill=True, align="R")
    pdf.cell(col_amt, 7, f"{total:,.2f}", border=1, fill=True, align="R", ln=True)

    # ── Footer ───────────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        190, 4,
        "This is a system generated statement and does not require a signature. "
        "For queries call 1800-202-6161 (toll free) or 1860-267-6161. "
        "HDFC Bank Ltd, Registered Office: HDFC Bank House, Senapati Bapat Marg, Lower Parel, Mumbai - 400013."
    )

    return pdf


def main():
    jan_pdf = build_pdf(
        month_label    = "01 Jan 2025 to 31 Jan 2025",
        statement_date = "31 Jan 2025",
        due_date       = "20 Feb 2025",
        transactions   = JANUARY,
    )
    jan_pdf.output("hdfc_january_2025.pdf")
    print("Created: hdfc_january_2025.pdf")

    feb_pdf = build_pdf(
        month_label    = "01 Feb 2025 to 28 Feb 2025",
        statement_date = "28 Feb 2025",
        due_date       = "20 Mar 2025",
        transactions   = FEBRUARY,
    )
    feb_pdf.output("hdfc_february_2025.pdf")
    print("Created: hdfc_february_2025.pdf")


if __name__ == "__main__":
    main()
