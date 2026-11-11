"""Conservative, explainable rules; no scores presented as probabilities."""
from dataclasses import asdict, dataclass
import re

from core.models import Intake, PRELIMINARY_NOTICE
from core.url_analysis import URLAnalysis, analyze_url


@dataclass
class Assessment:
    category: str
    priority: str
    indicators: list[str]
    explanation: str
    url_analysis: URLAnalysis

    def as_dict(self) -> dict:
        return asdict(self)


def assess(intake: Intake) -> Assessment:
    intake = intake.validated()
    url = analyze_url(intake.url, intake.official_domain)
    # Notes are investigator context, not suspicious page content.
    text = re.sub(r"\s+", " ", (intake.title + " " + intake.description).casefold())
    brand_present = bool(re.search(r"(?<!\w)" + re.escape(intake.brand.casefold()) + r"(?!\w)", text))
    credential = bool(re.search(r"\b(?:enter|provide|submit|confirm|share)\b.{0,45}\b(?:password|login credentials|one[- ]time (?:code|password)|otp|credit card|card details)\b", text))
    verification = bool(re.search(r"\b(?:verify your (?:account|identity)|account (?:suspended|locked)|security verification)\b", text))
    urgency = bool(re.search(r"\b(?:pay (?:now|immediately|within)|urgent payment|wire transfer|send (?:money|payment)|within \d+ (?:hours?|minutes?))\b", text))
    affiliation = bool(re.search(r"\b(?:official (?:store|support|partner|outlet|website)|authorized (?:dealer|reseller)|affiliated with)\b", text))
    counterfeit = bool(re.search(r"\b(?:replica|counterfeit|knock[- ]?off|fake designer|1:1 copy)\b", text))
    trademark = bool(re.search(r"\b(?:use (?:their|the) (?:logo|trademark)|copied (?:logo|trademark)|unauthorized (?:logo|trademark)|trademark misuse)\b", text))
    signals = []
    if credential:
        signals.append("Content requests credentials or sensitive payment details; verify the context manually.")
    if verification:
        signals.append("Content uses account verification, suspension, or security-verification language.")
    if urgency:
        signals.append("Content pressures the reader to make a payment or act within a short deadline.")
    if affiliation:
        signals.append("Content claims official affiliation or authorization; independent verification is needed.")
    if counterfeit:
        signals.append("Content contains replica/counterfeit terminology; this may also occur in warnings or discussions.")
    if trademark:
        signals.append("Content mentions potentially unauthorized logo or trademark use; context and rights require review.")
    resemblance = any("resembles" in i or "deceptive placement" in i for i in url.indicators)
    outside_official = bool(url.official_domain and url.hostname and not url.matches_official)
    if credential or (verification and urgency):
        category = "Potential phishing"
    elif counterfeit and intake.source_type == "Marketplace":
        category = "Potential counterfeit listing"
    elif affiliation and brand_present and outside_official:
        category = "Potential brand impersonation"
    elif trademark and brand_present:
        category = "Potential trademark misuse"
    elif resemblance:
        category = "Potential brand impersonation"
    else:
        category = "Other suspicious content"
    if credential and (verification or urgency) and not url.matches_official:
        priority = "High"
    elif credential or (verification and urgency) or (counterfeit and intake.source_type == "Marketplace") or (affiliation and brand_present and outside_official) or (trademark and brand_present) or resemblance:
        priority = "Medium"
    else:
        priority = "Low"
    indicators = url.indicators + signals
    explanation = (
        f"Suggested category: {category}. {priority} is a review priority, not a finding of wrongdoing. "
        + ("Priority reflects the specific signals listed below. " if indicators else "No configured risk signals were found; absence of signals does not establish safety. ")
        + ("The configured official host matches, so credential language alone is not treated as high priority. " if url.matches_official and credential else "")
        + "Rules match wording without understanding negation, quotations, permission or intent. "
        + PRELIMINARY_NOTICE
    )
    return Assessment(category, priority, indicators, explanation, url)
