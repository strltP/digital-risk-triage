import pytest
from core.url_analysis import analyze_url, normalize_url


@pytest.mark.parametrize('raw,host,registered', [
    ('Example.COM/path', 'example.com', 'example.com'),
    ('https://shop.example.co.uk/a', 'shop.example.co.uk', 'example.co.uk'),
    ('//ASTERVALE.EXAMPLE', 'astervale.example', 'astervale.example'),
    ('https://127.0.0.1/', '127.0.0.1', '127.0.0.1'),
    ('https://[2001:db8::1]:443/a', '2001:db8::1', '2001:db8::1'),
    ('https://bücher.example', 'xn--bcher-kva.example', 'xn--bcher-kva.example'),
])
def test_normalize(raw, host, registered):
    result = analyze_url(raw)
    assert result.hostname == host
    assert result.registered_domain == registered
    assert result.normalized_url.startswith('https://')


@pytest.mark.parametrize('raw', ['javascript:alert(1)', 'file:///etc/passwd', 'ftp://example.com',
    'https://', 'https://bad host.example', 'https://example.com:99999', 'https://bad_.example',
    'https://a..example', 'https://example.com\\@evil.example', 'https://[bad]'])
def test_invalid_urls(raw):
    with pytest.raises(ValueError):
        normalize_url(raw)


def test_official_boundary_and_deceptive_hostname():
    assert analyze_url('shop.astervale.example', 'astervale.example').matches_official
    result = analyze_url('astervale.example.attacker.example', 'astervale.example')
    assert not result.matches_official
    assert any('deceptive placement' in item for item in result.indicators)
    assert 'not a fraud probability' in result.comparison


def test_offline(monkeypatch):
    import requests.sessions
    def forbidden(*args, **kwargs):
        pytest.fail('URL analysis attempted a network request')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    result = analyze_url('https://a.b.c.example.co.uk/path?next=https://example.com', 'brand.example')
    assert any('subdomain' in i for i in result.indicators)
    assert any('embeds another URL' in i for i in result.indicators)


def test_userinfo_length_and_punycode():
    assert any('before @' in i for i in analyze_url('https://official.example@evil.example').indicators)
    assert any('long' in i for i in analyze_url('example.com/' + 'a' * 210).indicators)
    assert any('punycode' in i for i in analyze_url('bücher.example').indicators)


def test_official_requires_domain():
    with pytest.raises(ValueError):
        analyze_url('example.com', 'https://official.example/login')
    assert analyze_url('').hostname == ''


def test_common_suffix_and_short_names_do_not_raise_resemblance():
    result = analyze_url('x.example', 'y.example')
    assert result.similarity == 0
    assert not result.indicators
    result = analyze_url('asterva1e.example', 'astervale.example')
    assert result.similarity >= 80
    assert any('resembles' in item for item in result.indicators)
