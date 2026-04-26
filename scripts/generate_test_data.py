"""Generate three realistic test CSV files for a full Phase 3/4/5 demo.

Sessions created:
  - sbi savings       → salary + utility bills + credit card bill payments
  - hdfc credit card  → subscriptions, food, transport, shopping, entertainment
  - icici bank        → groceries, gym membership, healthcare, travel

Cross-session dedup test:
  - sbi savings has "HDFC Credit Card Bill Payment" and "ICICI Credit Card Bill Payment"
  - These should be excluded when running overall/cross-session queries

Subscription price-change test:
  - Netflix: ₹649 (Jan/Feb) → ₹699 (Mar)
  - Spotify: ₹119 (Jan/Feb) → ₹149 (Mar)

Run from project root:
  python scripts/generate_test_data.py
"""

import csv
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent

# ─────────────────────────────────────────────
# SBI SAVINGS — main salary account
# ─────────────────────────────────────────────
SBI_ROWS = [
    # ── January ──
    ("2025-01-01", "Salary Credit January 2025 NEFT",                 "85000.00"),
    ("2025-01-10", "BESCOM Electricity Bill Payment",                  "1200.00"),
    ("2025-01-15", "Airtel Broadband Bill Payment",                    "999.00"),
    ("2025-01-25", "Parag Parikh Flexi Cap Fund SIP",                  "5000.00"),

    # ── February ──
    ("2025-02-01", "Salary Credit February 2025 NEFT",                "85000.00"),
    # Inter-session transfer → "hdfc credit card" session (Jan bill payment)
    ("2025-02-05", "HDFC Credit Card Bill Payment",                   "18850.00"),
    ("2025-02-10", "BESCOM Electricity Bill Payment",                  "1350.00"),
    ("2025-02-12", "Airtel Broadband Bill Payment",                    "999.00"),
    # Inter-session transfer → "icici bank" session (Jan bill payment)
    ("2025-02-18", "ICICI Credit Card Bill Payment",                  "12400.00"),
    ("2025-02-25", "Parag Parikh Flexi Cap Fund SIP",                  "5000.00"),
    ("2025-02-28", "Groww Mutual Fund SIP Nifty 50",                   "3000.00"),

    # ── March ──
    ("2025-03-01", "Salary Credit March 2025 NEFT",                   "85000.00"),
    # Inter-session transfer → "hdfc credit card" session (Feb bill payment)
    ("2025-03-05", "HDFC Credit Card Bill Payment",                   "22650.00"),
    ("2025-03-08", "BESCOM Electricity Bill Payment",                  "1100.00"),
    ("2025-03-12", "Airtel Broadband Bill Payment",                    "999.00"),
    # Inter-session transfer → "icici bank" session (Feb bill payment)
    ("2025-03-18", "ICICI Credit Card Bill Payment",                  "10100.00"),
    ("2025-03-25", "Parag Parikh Flexi Cap Fund SIP",                  "5000.00"),
    ("2025-03-28", "Groww Mutual Fund SIP Nifty 50",                   "3000.00"),
    ("2025-03-31", "LIC Premium Payment Term Insurance",               "4500.00"),
]

# ─────────────────────────────────────────────
# HDFC CREDIT CARD — subscriptions + lifestyle
# ─────────────────────────────────────────────
# Jan total ≈ ₹18,850 | Feb total ≈ ₹22,650 | Mar total ≈ ₹20,100
# Subscription price increase in March: Netflix 649→699, Spotify 119→149
HDFC_ROWS = [
    # ── January ──
    ("2025-01-02", "Netflix.com Monthly Subscription",                   "649.00"),
    ("2025-01-02", "Spotify Premium Monthly Subscription",               "119.00"),
    ("2025-01-02", "YouTube Premium Subscription",                       "189.00"),
    ("2025-01-02", "Amazon Prime Video Subscription",                    "299.00"),
    ("2025-01-03", "Zomato food delivery order",                         "380.00"),
    ("2025-01-05", "Uber cab booking",                                   "250.00"),
    ("2025-01-07", "Swiggy food order",                                  "520.00"),
    ("2025-01-09", "Amazon.in electronics purchase",                    "3499.00"),
    ("2025-01-11", "Zomato food delivery order",                         "440.00"),
    ("2025-01-12", "BookMyShow movie tickets",                           "600.00"),
    ("2025-01-13", "Uber cab booking",                                   "195.00"),
    ("2025-01-15", "Swiggy food order",                                  "650.00"),
    ("2025-01-16", "Zomato Pro Annual membership",                       "299.00"),
    ("2025-01-18", "Myntra clothing purchase",                          "2499.00"),
    ("2025-01-19", "Uber cab booking",                                   "320.00"),
    ("2025-01-20", "Starbucks Coffee",                                   "680.00"),
    ("2025-01-22", "Zomato food delivery order",                         "350.00"),
    ("2025-01-23", "Flipkart fashion purchase",                         "1799.00"),
    ("2025-01-24", "Steam gaming purchase",                              "950.00"),
    ("2025-01-25", "Swiggy Instamart groceries",                         "890.00"),
    ("2025-01-26", "Ola cab booking",                                    "180.00"),
    ("2025-01-28", "Zomato food delivery order",                         "420.00"),
    ("2025-01-29", "Swiggy food order",                                  "480.00"),
    ("2025-01-30", "PVR Cinemas movie tickets",                          "700.00"),
    ("2025-01-31", "Uber cab booking",                                   "285.00"),
    ("2025-01-31", "Cafe Coffee Day",                                    "348.00"),

    # ── February ──
    ("2025-02-01", "Netflix.com Monthly Subscription",                   "649.00"),
    ("2025-02-01", "Spotify Premium Monthly Subscription",               "119.00"),
    ("2025-02-01", "YouTube Premium Subscription",                       "189.00"),
    ("2025-02-01", "Amazon Prime Video Subscription",                    "299.00"),
    ("2025-02-03", "Zomato food delivery order",                         "580.00"),
    ("2025-02-04", "Swiggy food order",                                  "480.00"),
    ("2025-02-05", "Uber cab booking",                                   "320.00"),
    ("2025-02-06", "Swiggy food order",                                  "520.00"),
    ("2025-02-07", "Amazon.in household items",                         "2199.00"),
    ("2025-02-08", "Zomato food delivery order",                         "380.00"),
    ("2025-02-10", "Myntra sale purchase",                              "3499.00"),
    ("2025-02-11", "Zomato food delivery order",                         "490.00"),
    ("2025-02-12", "Amazon fresh grocery delivery",                      "850.00"),
    ("2025-02-13", "BookMyShow concert tickets",                        "1200.00"),
    ("2025-02-14", "Uber cab booking",                                   "380.00"),
    ("2025-02-15", "Zomato Pro renewal membership",                      "299.00"),
    ("2025-02-16", "Swiggy Instamart groceries",                        "1100.00"),
    ("2025-02-17", "Zomato food delivery order",                         "410.00"),
    ("2025-02-18", "Ola cab booking",                                    "220.00"),
    ("2025-02-20", "Rapido bike ride",                                   "150.00"),
    ("2025-02-21", "Flipkart electronics purchase",                     "4999.00"),
    ("2025-02-22", "Swiggy food order",                                  "540.00"),
    ("2025-02-23", "Starbucks Coffee",                                   "720.00"),
    ("2025-02-24", "Zomato food delivery order",                         "350.00"),
    ("2025-02-25", "Uber cab booking",                                   "290.00"),
    ("2025-02-26", "PVR Cinemas movie tickets",                          "800.00"),
    ("2025-02-27", "Swiggy food order",                                  "455.00"),
    ("2025-02-28", "Zomato food delivery order",                         "312.00"),

    # ── March (Netflix +50, Spotify +30 price increase) ──
    ("2025-03-01", "Netflix.com Monthly Subscription",                   "699.00"),  # was 649
    ("2025-03-01", "Spotify Premium Monthly Subscription",               "149.00"),  # was 119
    ("2025-03-01", "YouTube Premium Subscription",                       "189.00"),
    ("2025-03-01", "Amazon Prime Video Subscription",                    "299.00"),
    ("2025-03-03", "Zomato food delivery order",                         "450.00"),
    ("2025-03-04", "Zomato food delivery order",                         "520.00"),
    ("2025-03-05", "Uber cab booking",                                   "280.00"),
    ("2025-03-07", "Swiggy food order",                                  "560.00"),
    ("2025-03-08", "Amazon.in purchase",                                "1899.00"),
    ("2025-03-09", "Swiggy food order",                                  "640.00"),
    ("2025-03-10", "Myntra sale purchase",                              "2299.00"),
    ("2025-03-11", "Zomato food delivery order",                         "380.00"),
    ("2025-03-13", "BookMyShow movie tickets",                           "550.00"),
    ("2025-03-14", "Zomato Pro renewal membership",                      "299.00"),
    ("2025-03-15", "Uber cab booking",                                   "350.00"),
    ("2025-03-16", "Rapido bike ride",                                   "180.00"),
    ("2025-03-17", "Swiggy Instamart groceries",                         "950.00"),
    ("2025-03-18", "Zomato food delivery order",                         "420.00"),
    ("2025-03-19", "Ola cab booking",                                    "190.00"),
    ("2025-03-20", "Amazon fresh grocery delivery",                      "780.00"),
    ("2025-03-21", "Flipkart fashion purchase",                         "1799.00"),
    ("2025-03-22", "Swiggy food order",                                  "490.00"),
    ("2025-03-23", "Starbucks Coffee",                                   "680.00"),
    ("2025-03-24", "Cafe Coffee Day",                                    "450.00"),
    ("2025-03-25", "Zomato food delivery order",                         "310.00"),
    ("2025-03-26", "Uber cab booking",                                   "260.00"),
    ("2025-03-27", "PVR Cinemas movie tickets",                          "650.00"),
    ("2025-03-28", "Steam gaming purchase",                              "750.00"),
    ("2025-03-29", "Swiggy food order",                                  "435.00"),
    ("2025-03-30", "Amazon.in electronics purchase",                    "2500.00"),
    ("2025-03-31", "Zomato food delivery order",                         "268.00"),
]

# ─────────────────────────────────────────────
# ICICI BANK — groceries, gym, healthcare, travel
# ─────────────────────────────────────────────
# Jan total ≈ ₹12,400 | Feb total ≈ ₹10,100 | Mar total ≈ ₹7,100
ICICI_ROWS = [
    # ── January ──
    ("2025-01-04", "Cult.fit gym membership",                          "2000.00"),
    ("2025-01-06", "BigBasket grocery shopping",                       "2500.00"),
    ("2025-01-10", "Netmeds pharmacy purchase",                         "850.00"),
    ("2025-01-12", "IRCTC train ticket booking Mumbai",                "1500.00"),
    ("2025-01-15", "Healthify Me premium subscription",                 "499.00"),
    ("2025-01-17", "Reliance Smart grocery shopping",                  "1800.00"),
    ("2025-01-19", "Apollo Pharmacy medicine",                          "650.00"),
    ("2025-01-22", "MakeMyTrip hotel booking Goa",                     "3500.00"),
    ("2025-01-28", "Doctor consultation fee",                           "800.00"),
    ("2025-01-30", "BigBasket grocery top-up",                         "1100.00"),

    # ── February ──
    ("2025-02-04", "Cult.fit gym membership",                          "2000.00"),
    ("2025-02-06", "BigBasket grocery shopping",                       "2200.00"),
    ("2025-02-09", "Netmeds pharmacy purchase",                         "420.00"),
    ("2025-02-10", "Healthify Me premium subscription",                 "499.00"),
    ("2025-02-13", "IRCTC train ticket booking",                       "2200.00"),
    ("2025-02-15", "Reliance Smart grocery shopping",                  "1800.00"),
    ("2025-02-20", "Apollo Pharmacy medicine",                          "380.00"),
    ("2025-02-24", "Doctor consultation fee",                           "500.00"),
    ("2025-02-28", "BigBasket grocery top-up",                          "950.00"),

    # ── March ──
    ("2025-03-04", "Cult.fit gym membership",                          "2000.00"),
    ("2025-03-07", "BigBasket grocery shopping",                       "1900.00"),
    ("2025-03-11", "Netmeds pharmacy purchase",                         "650.00"),
    ("2025-03-14", "Healthify Me premium subscription",                 "499.00"),
    ("2025-03-18", "Reliance Smart grocery shopping",                  "1400.00"),
    ("2025-03-22", "Apollo Pharmacy medicine",                          "520.00"),
    ("2025-03-27", "Doctor consultation fee",                           "700.00"),
    ("2025-03-29", "BigBasket grocery top-up",                          "550.00"),
]


def write_csv(filename: str, rows: list[tuple[str, str, str]]) -> Path:
    path = OUTPUT_DIR / filename
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "description", "amount"])
        writer.writerows(rows)
    total = sum(float(r[2]) for r in rows)
    print(f"  {filename}: {len(rows)} rows, total ₹{total:,.2f}")
    return path


if __name__ == "__main__":
    print("Generating test CSV files...\n")

    write_csv("sbi_savings_jan_mar_2025.csv", SBI_ROWS)
    write_csv("hdfc_cc_jan_mar_2025.csv", HDFC_ROWS)
    write_csv("icici_jan_mar_2025.csv", ICICI_ROWS)

    print("""
Done. Three CSV files written to the project root.

─────────────────────────────────────────────────────────────
IMPORT ORDER (tell Claude Desktop in this order):
─────────────────────────────────────────────────────────────

1. Delete all existing sessions:
   "Delete all sessions"

2. Import SBI savings statement:
   "Import /path/to/sbi_savings_jan_mar_2025.csv into session 'sbi savings'"

3. Import HDFC credit card statement:
   "Import /path/to/hdfc_cc_jan_mar_2025.csv into session 'hdfc credit card'"

4. Import ICICI bank statement:
   "Import /path/to/icici_jan_mar_2025.csv into session 'icici bank'"

─────────────────────────────────────────────────────────────
WHAT TO TEST:
─────────────────────────────────────────────────────────────

Phase 3 — Transactions:
  • "Show my spending from January to March" (overall — should deduplicate)
  • "Show my HDFC spending from January to March"
  • "Compare January and February spending on my HDFC card"

Phase 4 — Subscriptions:
  • "Detect subscriptions on my HDFC credit card"
  • "Audit my subscriptions"
  • "Any subscription price increases?" (Netflix +₹50, Spotify +₹30)

Phase 5 — Scenarios:
  • "If I cut food spending by 40%, how long to save ₹90,000 for a MacBook Pro?"
  • "If I cut food by 40% overall, when can I afford ₹1,50,000 Goa trip?"
  • (overall query should use deduplicated cross-session baseline)

Cross-session dedup test:
  • "What is my total overall spending Jan–Mar excluding savings?"
  • Should show a note: "(Excluded N inter-session transfer(s))"
  • SBI's HDFC/ICICI bill payments should NOT appear in category totals
""")
