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
    for kwargs in ({'url': '', 'description': '?!'}, {'brand': ''}, {'source_type': 'Unknown'}):
        with pytest.raises(ValueError):
            assess(intake(**kwargs))
