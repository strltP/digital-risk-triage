"""Twelve fictional scenarios on reserved .example domains; never evidence."""
from core.database import Database
from core.models import Intake

# source, URL, brand, official domain, title, content, simulated disposition
SCENARIOS = [
    ("Website", "https://astervale-security.example/login", "Astervale", "astervale.example",
     "Account alert", "Verify your account. Enter your password within 2 hours.", None),
    ("Social Media", "https://social.example/lumifern-help", "Lumifern", "lumifern.example",
     "Security message", "Account suspended. Provide your one-time code. Pay now to unlock.", None),
    ("Website", "https://asterva1e.example", "Astervale", "astervale.example",
     "Astervale official store", "Astervale official outlet for customer support.", None),
    ("Social Media", "https://social.example/lumifern", "Lumifern", "lumifern.example",
     "Lumifern partner page", "Lumifern authorized dealer. Affiliation requires checking.", None),
    ("Marketplace", "https://market.example/listings/101", "Velora Works", "veloraworks.example",
     "Replica bag", "Velora Works replica bag, 1:1 copy.", None),
    ("Marketplace", "https://market.example/listings/102", "Northpetal", "northpetal.example",
     "Designer-style listing", "Northpetal knock-off jacket; authenticity unverified.", None),
    ("Website", "https://design.example/portfolio", "Velora Works", "veloraworks.example",
     "Logo portfolio", "Velora Works copied logo on unrelated merchandise; rights unknown.", None),
    ("Other", "https://print.example/catalog", "Northpetal", "northpetal.example",
     "Print sample", "Northpetal unauthorized trademark on printed goods, reported by submitter.", None),
    ("Website", "https://astervale.example/login", "Astervale", "astervale.example",
     "Normal official login", "Verify your account. Enter your password on the usual sign-in page.",
     "SIMULATED REVIEW: official login verified against fictional internal records. Credential language alone is not a violation."),
    ("Marketplace", "https://market.example/safety-guide", "Velora Works", "veloraworks.example",
     "Counterfeit awareness guide", "How to recognize a Velora Works replica or counterfeit bag. Educational warning.",
     "SIMULATED REVIEW: educational warning, not a sale. Keyword rules lack context; no violation found."),
    ("Website", "https://astervale-outlet.example", "Astervale", "astervale.example",
     "Authorized outlet", "Astervale official outlet. Dealer authorization provided for review.",
     "SIMULATED REVIEW: fictional brand owner confirmed dealer authorization. A similar domain and affiliation claim were not proof."),
    ("Website", "https://lumifern.example/products", "Lumifern", "lumifern.example",
     "Seasonal catalogue", "Great deals on Lumifern quality products. Seasonal catalogue.", None),
]


def load_demo(db: Database) -> int:
    inserted = 0
    for index, (source, url, brand, official, title, content, disposition) in enumerate(SCENARIOS, 1):
        key = f"demo-v1-{index:02d}"
        with db.connection() as conn:
            if conn.execute("SELECT 1 FROM cases WHERE demo_key=?", (key,)).fetchone():
                continue  # Preserve any subsequent investigator edits.
        case_id = db.create_case(Intake(source, url, brand, official,
                                       "[SIMULATED] " + title, content,
                                       "SIMULATED DEMO — fictional scenario; no real evidence or allegation."), demo_key=key)
        if disposition:
            db.update_review(case_id, notes=disposition, status="False Positive", verdict="No violation found")
        elif index == 4:
            db.update_review(case_id, notes="SIMULATED DEMO — checking claimed authorization; no verdict yet.",
                             status="Reviewing", verdict="Inconclusive")
        inserted += 1
    return inserted
