"""Idempotent 100-case sample dataset, compatible with the original 12 keys."""
from core.database import Database
from core.sample_scenarios import ADDITIONAL_SCENARIOS, Scenario

# source, URL, brand, official domain, title, content, simulated disposition
LEGACY_SCENARIOS = [
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
     "Official login matches fictional internal records. Credential language alone is not a violation."),
    ("Marketplace", "https://market.example/safety-guide", "Velora Works", "veloraworks.example",
     "Counterfeit awareness guide", "How to recognize a Velora Works replica or counterfeit bag. Educational warning.",
     "Educational warning, not a sale. Keyword rules lack context; no violation found."),
    ("Website", "https://astervale-outlet.example", "Astervale", "astervale.example",
     "Authorized outlet", "Astervale official outlet. Dealer authorization provided for review.",
     "The exercise includes dealer authorization. A similar domain and affiliation claim were not proof."),
    ("Website", "https://lumifern.example/products", "Lumifern", "lumifern.example",
     "Seasonal catalogue", "Great deals on Lumifern quality products. Seasonal catalogue.", None),
]

SCENARIOS = tuple(
    Scenario(
        f"demo-v1-{index:02d}", source, url, brand, title, content,
        status="False Positive" if disposition else "Reviewing" if index == 4 else "New",
        review_notes=disposition or ("Checking claimed authorization; no verdict yet." if index == 4 else ""),
    )
    for index, (source, url, brand, _official, title, content, disposition) in enumerate(LEGACY_SCENARIOS, 1)
) + ADDITIONAL_SCENARIOS


def load_demo(db: Database) -> int:
    """Insert only missing stable keys; never update an existing investigation.

    Reviews use the public validation path, including validation before escalation.
    The returned count reports new records, not the total size of the dataset.
    """
    inserted = 0
    for scenario in SCENARIOS:
        with db.connection() as conn:
            if conn.execute("SELECT 1 FROM cases WHERE demo_key=?", (scenario.key,)).fetchone():
                continue  # Preserve any subsequent investigator edits.
        intake = scenario.intake()
        case_id = db.create_case(intake, demo_key=scenario.key)
        if scenario.status == "Escalated":
            db.update_review(case_id, notes=intake.notes, status="Validated", verdict=scenario.verdict)
        if scenario.status != "New":
            db.update_review(case_id, notes=intake.notes, status=scenario.status, verdict=scenario.verdict)
        inserted += 1
    return inserted
