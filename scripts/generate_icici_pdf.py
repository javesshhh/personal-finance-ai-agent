"""Generate a dummy ICICI credit card statement PDF for March 2025."""

from fpdf import FPDF

MARCH = [
    ("01 Mar 2025", "Swiggy - Dinner Order",              "520.00"),
    ("02 Mar 2025", "Uber India - Trip",                   "210.00"),
    ("03 Mar 2025", "Amazon India - Accessories",          "1299.00"),
    ("04 Mar 2025", "Zomato Ltd",                          "440.00"),
    ("05 Mar 2025", "BigBasket Online Groceries",          "2100.00"),
    ("06 Mar 2025", "Rapido Technologies",                  "90.00"),
    ("07 Mar 2025", "BESCOM Electricity Bill",             "1560.00"),
    ("08 Mar 2025", "Swiggy - Womens Day Special",         "1100.00"),
    ("09 Mar 2025", "PhonePe UPI - Rent Payment",         "18000.00"),
    ("10 Mar 2025", "Ola Cabs - Ride",                     "260.00"),
    ("11 Mar 2025", "Netflix India",                        "649.00"),
    ("12 Mar 2025", "Zomato - Breakfast",                   "230.00"),
    ("13 Mar 2025", "Swiggy Instamart",                     "690.00"),
    ("14 Mar 2025", "Rapido - Bike Ride",                    "85.00"),
    ("15 Mar 2025", "Spotify Premium",                      "119.00"),
    ("17 Mar 2025", "Zomato - Holi Special",                "780.00"),
    ("18 Mar 2025", "BookMyShow - IPL Tickets",            "2400.00"),
    ("19 Mar 2025", "Uber India - Commute",                 "195.00"),
    ("20 Mar 2025", "DMart Retail - Shopping",             "3100.00"),
    ("21 Mar 2025", "Amazon India - Books",                  "850.00"),
    ("22 Mar 2025", "Swiggy - Lunch",                        "420.00"),
    ("23 Mar 2025", "MakeMyTrip - Hotel Goa",             "12000.00"),
    ("24 Mar 2025", "Zomato - Dinner",                       "610.00"),
    ("25 Mar 2025", "Airtel Prepaid Recharge",               "299.00"),
    ("26 Mar 2025", "Blinkit Quick Commerce",                "760.00"),
    ("27 Mar 2025", "Rapido Bike Ride",                      "100.00"),
    ("28 Mar 2025", "Swiggy - Weekend Brunch",               "840.00"),
    ("29 Mar 2025", "PharmEasy - Medicine",                  "470.00"),
    ("30 Mar 2025", "Zomato - Late Night",                   "350.00"),
    ("31 Mar 2025", "Cult.fit Gym Membership",              "1500.00"),
]


def build_pdf(transactions: list) -> FPDF:
    pdf = FPDF()
    pdf.add_page()

    # ── Header bar ──────────────────────────────────────────────────────────
    pdf.set_fill_color(240, 90, 40)      # ICICI orange
    pdf.rect(0, 0, 210, 28, style="F")

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 7)
    pdf.cell(0, 10, "ICICI Bank Credit Card Statement", ln=True)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(10, 18)
    pdf.cell(0, 6, "ICICI Bank Ltd  |  Credit Cards Division  |  ICICI Bank Towers, Bandra-Kurla Complex, Mumbai - 400051")

    # ── Account summary box ──────────────────────────────────────────────────
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(10, 35)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(255, 240, 230)
    pdf.cell(190, 7, "Account Summary", ln=True, fill=True)

    total = sum(float(t[2].replace(",", "")) for t in transactions)

    summary = [
        ("Statement Period",     "01 Mar 2025 to 31 Mar 2025"),
        ("Statement Date",       "31 Mar 2025"),
        ("Payment Due Date",     "20 Apr 2025"),
        ("Total Amount Due",     f"Rs. {total:,.2f}"),
        ("Minimum Amount Due",   f"Rs. {total * 0.05:,.2f}"),
        ("Credit Limit",         "Rs. 5,00,000.00"),
        ("Available Credit Limit", f"Rs. {500000 - total:,.2f}"),
        ("Card Number",          "XXXX XXXX XXXX 4821"),
        ("Reward Points Balance","3,240"),
    ]

    pdf.set_font("Helvetica", "", 9)
    col_w = 95
    for label, value in summary:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_w, 6, label, border=0)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_w, 6, value, border=0, ln=True)

    # ── Transaction table ────────────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_fill_color(240, 90, 40)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)

    col_date = 32
    col_desc = 118
    col_amt  = 40

    pdf.cell(col_date, 7, "Date",         border=1, fill=True, align="C")
    pdf.cell(col_desc, 7, "Description",  border=1, fill=True, align="C")
    pdf.cell(col_amt,  7, "Amount (Rs)",  border=1, fill=True, align="C", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)

    for i, (txn_date, description, amount) in enumerate(transactions):
        fill = i % 2 == 0
        pdf.set_fill_color(255, 245, 238) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.cell(col_date, 6, txn_date,    border=1, fill=fill, align="C")
        pdf.cell(col_desc, 6, description, border=1, fill=fill)
        pdf.cell(col_amt,  6, amount,      border=1, fill=fill, align="R", ln=True)

    # ── Totals row ───────────────────────────────────────────────────────────
    pdf.set_fill_color(240, 200, 175)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_date + col_desc, 7, "Total Charges", border=1, fill=True, align="R")
    pdf.cell(col_amt, 7, f"{total:,.2f}", border=1, fill=True, align="R", ln=True)

    # ── Footer ───────────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        190, 4,
        "This is a system generated statement. For disputes or queries, call ICICI Bank 24x7 helpline: "
        "1800-1080 (toll free) or 022-3366-7777. "
        "ICICI Bank Ltd, Registered Office: ICICI Bank Tower, Near Chakli Circle, Old Padra Road, Vadodara - 390007."
    )

    return pdf


def main():
    pdf = build_pdf(MARCH)
    pdf.output("icici_march_2025.pdf")
    print("Created: icici_march_2025.pdf")


if __name__ == "__main__":
    main()
