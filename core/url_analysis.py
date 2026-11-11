"""URL string inspection only. This module never connects to submitted hosts."""
from dataclasses import dataclass, field
import ipaddress
import re
from urllib.parse import unquote, urlsplit, urlunsplit

from rapidfuzz.fuzz import ratio
import tldextract

# Use the package's bundled Public Suffix List. No runtime downloads or cache.
EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


@dataclass
class URLAnalysis:
    normalized_url: str = ""
    hostname: str = ""
    registered_domain: str = ""
    official_domain: str = ""
    matches_official: bool = False
    similarity: float | None = None
    comparison: str = "No official domain supplied; similarity was not assessed."
    indicators: list[str] = field(default_factory=list)


def normalize_url(value: str) -> tuple[str, str]:
    value = value.strip()
    if not value:
        return "", ""
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("URLs cannot contain whitespace, control characters, or backslashes.")
    if len(value) > 4096:
        raise ValueError("URL exceeds the 4,096-character limit.")
    if value.startswith("//"):
        value = "https:" + value
    elif "://" not in value:
        # A host:port is valid; javascript:, mailto: and other schemes are not.
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) and not re.match(r"^[^/:]+:\d+(?:/|$)", value):
            raise ValueError("Only HTTP and HTTPS URLs are supported.")
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https"):
            raise ValueError("Only HTTP and HTTPS URLs are supported.")
        raw_host = (parsed.hostname or "").rstrip(".")
        port = parsed.port  # Validate port syntax/range even though no connection occurs.
        if not raw_host:
            raise ValueError("Enter a URL with a hostname.")
        try:
            address = ipaddress.ip_address(raw_host)
            host = address.compressed
            net_host = f"[{host}]" if address.version == 6 else host
        except ValueError:
            host = raw_host.encode("idna").decode("ascii").lower()
            if len(host) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
                raise ValueError("Enter a valid hostname.")
            net_host = host
        userinfo = parsed.netloc.rsplit("@", 1)[0] + "@" if "@" in parsed.netloc else ""
        netloc = userinfo + net_host + (f":{port}" if port is not None else "")
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, parsed.fragment)), host
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Invalid URL: {exc}") from exc


def registered_domain(host: str) -> str:
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        result = EXTRACT(host)
        # .example and other unknown suffixes have no PSL entry. Show a best-effort
        # last-two-label domain; never infer trust from this fallback.
        return result.top_domain_under_public_suffix or ".".join(host.split(".")[-2:])


def analyze_url(value: str, official: str = "", *, compare_official: bool = True) -> URLAnalysis:
    normalized, host = normalize_url(value)
    result = URLAnalysis(normalized_url=normalized, hostname=host)
    if official.strip():
        official_url, official_host = normalize_url(official)
        parts = urlsplit(official_url)
        if parts.username is not None or parts.path != "/" or parts.query or parts.fragment or parts.port is not None:
            raise ValueError("Official domain must be a hostname, optionally with http(s)://, without a path, port or login.")
        result.official_domain = official_host
    if not host:
        result.comparison = "No suspicious URL supplied; domain comparison was not possible."
        return result
    result.registered_domain = registered_domain(host)
    parts = urlsplit(normalized)
    try:
        ipaddress.ip_address(host)
        result.indicators.append("Host is an IP address rather than a domain name.")
    except ValueError:
        pass
    if any(label.startswith("xn--") for label in host.split(".")):
        result.indicators.append("Hostname uses punycode/Unicode; visually inspect for lookalike characters.")
    subdomain = EXTRACT(host).subdomain
    if len(subdomain.split(".")) >= 3 and subdomain:
        result.indicators.append("Hostname has unusually many subdomain levels.")
    if parts.username is not None:
        result.indicators.append("URL contains login information before @, which can obscure the actual host.")
    if len(normalized) > 200:
        result.indicators.append("URL is unusually long (over 200 characters).")
    if re.search(r"https?://", unquote(parts.path + "?" + parts.query), re.I):
        result.indicators.append("URL embeds another URL in its path or query; inspect the destination manually.")
    if result.official_domain and compare_official:
        official_registered = registered_domain(result.official_domain)
        result.matches_official = host == result.official_domain or host.endswith("." + result.official_domain)
        # Shared suffixes (especially .example) must not make unrelated short
        # names look similar. Compare the registrable name labels only.
        name = EXTRACT(result.registered_domain).domain if EXTRACT(result.registered_domain).suffix else result.registered_domain.split(".")[0]
        official_name = EXTRACT(official_registered).domain if EXTRACT(official_registered).suffix else official_registered.split(".")[0]
        result.similarity = round(ratio(name, official_name), 1)
        result.comparison = (
            f"Compared registered domain '{result.registered_domain}' with '{official_registered}': "
            f"{result.similarity}/100 name-label character similarity, excluding the suffix (not a fraud probability). "
            + ("The host is the configured official domain or its subdomain. This does not establish that its content is safe."
               if result.matches_official else "The host is outside the configured official domain. Similarity or a different domain alone does not establish impersonation.")
        )
        if not result.matches_official and result.registered_domain != official_registered and min(len(name), len(official_name)) >= 4 and result.similarity >= 80:
            result.indicators.append("Domain resembles the configured official domain but is outside it.")
        if not result.matches_official and result.official_domain in host:
            result.indicators.append("Official domain text appears inside a different hostname (possible deceptive placement).")
    elif result.official_domain:
        result.comparison = "Official domain recorded. Brand comparison was skipped because no protected brand name was supplied."
    return result
