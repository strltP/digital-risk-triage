import pytest
from core.models import Intake
from core.risk_rules import assess


def intake(**kwargs):
    return Intake(**(dict(source_type='Website', brand='Astervale',
                        url='https://astervale-support.example', official_domain='astervale.example') | kwargs))


def test_phishing_requires_combined_signals_for_high():
    result = assess(intake(description='Verify your account. Enter your password within 2 hours.'))
    assert result.category == 'Potential phishing'
    assert result.priority == 'High'
    assert 'Human verification' in result.explanation
    assert assess(intake(description='Enter your password')).priority == 'Medium'


def test_official_login_is_not_high():
    result = assess(intake(url='https://astervale.example/login', description='Verify your account. Enter your password.'))
    assert result.priority == 'Medium'
    assert 'official host matches' in result.explanation


@pytest.mark.parametrize('kwargs,category', [
    ({'source_type': 'Marketplace', 'description': 'Astervale replica handbag, 1:1 copy'}, 'Potential counterfeit listing'),
    ({'description': 'Astervale official store'}, 'Potential brand impersonation'),
    ({'description': 'Astervale copied logo on an unrelated site'}, 'Potential trademark misuse'),
])
def test_categories(kwargs, category):
    assert assess(intake(**kwargs)).category == category


def test_https_and_marketing_and_notes_are_not_risk_signals():
    result = assess(intake(url='https://unrelated.example', description='Great deals and quality products today!', notes='enter your password'))
    assert result.priority == 'Low'
    assert not result.indicators


def test_no_official_domain_means_no_similarity_inference():
    result = assess(intake(official_domain='', description='Astervale official store'))
    assert result.url_analysis.similarity is None
    assert result.priority == 'Low'


def test_content_only_and_validation():
    assert assess(intake(url='', description='Astervale suspicious marketplace content')).priority == 'Low'
    for kwargs in ({'url': '', 'description': '?!'}, {'brand': 'A'}, {'source_type': 'Unknown'}):
        with pytest.raises(ValueError):
            assess(intake(**kwargs))


@pytest.mark.parametrize('brand', ['', '   '])
def test_general_phishing_does_not_require_brand(brand):
    result = assess(intake(brand=brand, official_domain='',
                           description='Verify your account. Enter your password within 2 hours.'))
    assert result.category == 'Potential phishing'
    assert result.priority == 'High'
    assert result.url_analysis.similarity is None
    assert 'Brand-specific checks were skipped' in result.explanation


@pytest.mark.parametrize('source,description', [
    ('Website', 'An official store with a copied logo and unauthorized trademark.'),
    ('Marketplace', 'Replica handbag and counterfeit product, official outlet.'),
    ('Other', 'Reported abusive messages aimed at an online community.'),
])
def test_brandless_content_does_not_trigger_brand_rules(source, description):
    result = assess(Intake(source, brand='', description=description))
    assert result.category == 'Other suspicious content'
    assert result.priority == 'Low'
    assert result.indicators == []


def test_official_domain_alone_is_not_brand_comparison():
    result = assess(intake(brand='', url='https://asterva1e.example', description='Official store'))
    assert result.url_analysis.official_domain == 'astervale.example'
    assert result.url_analysis.similarity is None
    assert not result.url_analysis.matches_official
    assert 'no protected brand name' in result.url_analysis.comparison
    assert result.priority == 'Low'
    assert result.indicators == []


def test_brand_rules_require_reference_to_named_brand():
    result = assess(intake(url='https://market.example', source_type='Marketplace',
                           description='Replica handbag, copied logo, official outlet.'))
    assert result.category == 'Other suspicious content'
    assert result.priority == 'Low'
    assert result.indicators == []
    # A name is sufficient for text checks, but not domain comparison.
    named = assess(intake(official_domain='', description='Astervale copied logo'))
    assert named.category == 'Potential trademark misuse'
    assert named.url_analysis.similarity is None


def test_unbranded_url_structural_checks_still_run():
    result = assess(Intake('Website', 'http://127.0.0.1/'))
    assert any('IP address' in indicator for indicator in result.indicators)
    assert result.url_analysis.similarity is None


def test_domain_only_input_still_validates_official_domain():
    with pytest.raises(ValueError, match='Official domain'):
        assess(Intake('Website', 'https://example.com', official_domain='https://brand.example/login'))
