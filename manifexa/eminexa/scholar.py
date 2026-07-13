"""Google-Scholar seed support — the leading-edge input.

Google Scholar has no API and blocks scrapers, but a *single* profile page
fetched with a browser User-Agent returns clean HTML with stable class names.
We parse the name, current affiliation, verified-email domain, and the top paper
titles, then **paper-anchor** to an OpenAlex author id: search each title on
OpenAlex, keep the author whose name matches the profile, and take the id that
the most papers corroborate. This is non-deterministic by nature (a search →
verify), so a weak match raises ``ScholarUnresolved`` rather than guessing.

The fetch is injectable so the parse/anchor logic is unit-tested offline.
"""
from __future__ import annotations

import collections
import html
import re
import unicodedata
import urllib.request
from dataclasses import dataclass, field

from ..sources.openalex import normalize_openalex_id

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122 Safari/537.36")
_SCHOLAR_ID = re.compile(r"[?&]user=([\w-]+)")


class ScholarUnresolved(ValueError):
    """Raised when a Scholar profile can't be confidently anchored to OpenAlex."""


@dataclass
class ScholarProfile:
    name: str
    affiliation: str = ""
    email_domain: str = ""
    titles: list[str] = field(default_factory=list)
    publications: list[dict] = field(default_factory=list)


def is_scholar_url(s: str) -> bool:
    return "scholar.google." in (s or "")


def parse_scholar_id(url: str) -> str | None:
    m = _SCHOLAR_ID.search(url or "")
    return m.group(1) if m else None


def _first(pattern: str, text: str, flags=0) -> str:
    m = re.search(pattern, text, flags)
    return html.unescape(m.group(1)).strip() if m else ""


def _strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def _cell(pattern: str, row: str) -> str:
    m = re.search(pattern, row, re.S)
    return html.unescape(_strip_tags(m.group(1))).strip() if m else ""


def parse_publications(text: str) -> list[dict]:
    """Every publication row on the profile: title, authors (abbreviated as
    Scholar shows them), venue, year, and Scholar's citation count."""
    pubs = []
    for row in re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', text, re.S):
        title = _cell(r'class="gsc_a_at"[^>]*>(.*?)</a>', row)
        if not title:
            continue
        grays = re.findall(r'class="gs_gray">(.*?)</div>', row, re.S)
        cites_txt = _cell(r'class="gsc_a_ac[^"]*"[^>]*>(.*?)</a>', row)
        pubs.append({
            "title": title,
            "authors": html.unescape(_strip_tags(grays[0])).strip() if grays else "",
            "venue": html.unescape(_strip_tags(grays[1])).strip() if len(grays) > 1 else "",
            "year": _cell(r'class="gsc_a_h[^"]*"[^>]*>(.*?)</span>', row),
            "cites": int(cites_txt) if cites_txt.isdigit() else 0,
        })
    return pubs


def parse_profile(text: str) -> ScholarProfile:
    """Pull name / affiliation / email-domain / paper titles / full publication
    list from Scholar HTML."""
    name = _first(r'id="gsc_prf_in">([^<]+)', text)
    aff_raw = re.search(r'<div class="gsc_prf_il"[^>]*>(.*?)</div>', text, re.S)
    affiliation = html.unescape(_strip_tags(aff_raw.group(1))) if aff_raw else ""
    email_domain = _first(r"Verified email at ([^\s<]+)", text)
    titles = [html.unescape(t).strip() for t in re.findall(r'class="gsc_a_at"[^>]*>([^<]+)', text)]
    return ScholarProfile(name=name, affiliation=affiliation, email_domain=email_domain,
                          titles=titles, publications=parse_publications(text))


def fetch_profile(url: str, timeout: int = 15, pagesize: int = 100) -> str:
    """Fetch a Scholar profile page as HTML (browser UA; a single polite GET).
    ``pagesize`` up to 100 returns the full publication list in one request — the
    default profile page shows only 20."""
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}cstart=0&pagesize={pagesize}"
    req = urllib.request.Request(full, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _norm(s: str) -> str:
    """Normalise a name for matching: drop parenthetical nicknames
    ('… (Leno)'), strip accents ('Schäfer' → 'schafer'), fold case/space."""
    s = re.sub(r"\(.*?\)", " ", html.unescape(s or ""))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().casefold()


def _name_match(scholar: str, oa: str) -> bool:
    """Same person? surname must match and first-name initial must match — lenient
    enough for 'Geoffrey Hinton' ↔ 'Geoffrey E. Hinton', strict on the surname."""
    a, b = _norm(scholar).split(), _norm(oa).split()
    if not a or not b:
        return False
    return a[-1] == b[-1] and a[0][:1] == b[0][:1]


def resolve_scholar(pc, profile: ScholarProfile, top: int = 6, min_corr: int = 2) -> dict:
    """Paper-anchor a Scholar profile to an OpenAlex author id. Searches the top
    ``top`` titles, tallies name-matching author ids, and returns the id the most
    papers corroborate. Raises ``ScholarUnresolved`` below ``min_corr`` matches."""
    tally: collections.Counter = collections.Counter()
    names: dict[str, str] = {}
    searched = 0
    for title in profile.titles[:top]:
        if not title:
            continue
        searched += 1
        works = pc.search_works(title, per_page=1)
        if not works:
            continue
        for sh in works[0].get("authorships", []):
            au = sh.get("author") or {}
            if _name_match(profile.name, au.get("display_name", "")):
                k = normalize_openalex_id(au.get("id", ""))
                if k:
                    tally[k] += 1
                    names[k] = au.get("display_name", "")
    if not tally:
        raise ScholarUnresolved(
            f"couldn't match '{profile.name}' to any OpenAlex author across {searched} papers")
    win, corr = tally.most_common(1)[0]
    if corr < min_corr:
        raise ScholarUnresolved(
            f"weak match for '{profile.name}' — only {corr}/{searched} papers point at {win}; not confident")
    return {"author_id": win, "author_name": names[win], "corroboration": corr,
            "searched": searched, "candidates": dict(tally)}
