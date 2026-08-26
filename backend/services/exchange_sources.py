"""Admin-configurable USD->IRT exchange-rate sources: Bonbast.com (a real
built-in fetcher, DB-registered) and any additional site an admin adds from
the panel with no deploy (backend/exchange_rate_admin.py's
/admin/exchange-rate/sources endpoints, migrations/0047_exchange_sources.sql).

Owner's ask (2026-08-25, Persian, see NEXT-SESSION.md): pull the USD rate
from Bonbast.com next to tgju.org, and leave the source list open so a
future reference site can be added from the panel without a deploy.

── Where this plugs into content.py's resolver ─────────────────────────
content.py's _compute_exchange_rate() keeps its original 4-tier ladder
(db_override -> tgju -> er_api -> hardcoded_fallback) byte-for-byte --
tests/test_exchange_rate_source.py patches content._fetch_tgju_rate
directly and asserts that exact tier order, so it was not touched. This
module supplies one EXTRA rung, resolve_configured_sources(), which
content.py tries only when tgju has already failed and only before falling
back to open.er-api.com. It walks every enabled row of
exchange_rate_sources (Bonbast plus any admin-added custom_regex row) in
priority order and returns the first candidate that both fetches
successfully and passes is_plausible_usd_irt_toman() below.

── Trust boundary (custom_regex sources) ────────────────────────────────
An admin-supplied source is a URL plus a DECLARATIVE extraction rule --
never code. There is no eval/exec/arbitrary-expression path anywhere in
this file. Two admin-supplied things are treated as hostile input and
bounded accordingly:
  1. The regex itself: applied only through _bounded_search(), which caps
     the haystack to _MAX_EXTRACT_TEXT_BYTES *before* matching and enforces
     a hard wall-clock budget via SIGALRM, so a catastrophic-backtracking
     pattern can never hang a request. validate_custom_regex_pattern() adds
     a best-effort heuristic rejection of the most common ReDoS shapes at
     write time; the SIGALRM budget is the real backstop, not the
     heuristic.
  2. The URL: validate_source_url() is a best-effort SSRF guard applied at
     write time (scheme must be https, hostname must not be a known
     internal name or a private/loopback/link-local IP literal). This does
     NOT defend DNS rebinding (a hostname that resolves to a public IP at
     write time and an internal one at fetch time) -- the primary gate here
     is that only an authenticated admin (admin_required, single owner
     account today) can reach these endpoints at all, the same trust level
     already required to edit prices, wallets, and everything else in the
     admin panel. _fetch_custom_regex_rate() adds one more layer at fetch
     time: follow_redirects=False, so an initially-safe HTTPS URL can never
     redirect its way to an internal host on a later request.

── IMPORT CONTRACT ──────────────────────────────────────────────────────
`import content` at module scope only (no `content.<attr>` access until a
function actually runs) -- the same late-binding pattern content_eur_rate.py
uses for content.<name>, documented in content.py's own module docstring.
Safe against the content.py <-> services.exchange_sources circular import:
content.py only ever imports this module from *inside* a function body
(_compute_exchange_rate()), never at its own module scope, so by the time
this module's `import content` runs, content.py has always already
finished executing.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import signal
from typing import Any
from urllib.parse import urlparse

import sqlalchemy

from database import async_session, rds

import content

logger = logging.getLogger('content')  # keep exchange-rate logs under the pre-split 'content' logger name

# ── Sanity band ───────────────────────────────────────────────────────────
# An order-of-magnitude guard against a bad scrape or a Rial/Toman
# unit-conversion bug landing in the catalogue -- NOT an attempt to track
# the real market day to day. Verified live against bonbast.com on
# 2026-08-25: usd1 = 203,700 Toman, comfortably inside this envelope.
# Revisit only if genuine inflation ever pushes the real market rate
# outside it.
SANITY_MIN_TOMAN = 10_000.0
SANITY_MAX_TOMAN = 5_000_000.0


def is_plausible_usd_irt_toman(rate_toman: Any) -> bool:
    """True if `rate_toman` is a real, finite number inside the sanity band.
    Used on every fetched candidate before it is ever allowed to win a
    tier -- see the module docstring."""
    try:
        r = float(rate_toman)
    except (TypeError, ValueError):
        return False
    if r != r or r in (float('inf'), float('-inf')):  # NaN / inf
        return False
    return SANITY_MIN_TOMAN <= r <= SANITY_MAX_TOMAN


# ── Flat Toman markup (owner-editable) ────────────────────────────────────
# 2026-08-25: the owner asked for the flat Toman markup on the USD->IRT rate
# (content.py's USD_IRT_FLAT_MARKUP, previously env-var-only) to be editable
# from the admin panel instead of requiring a rebuild. Stored the same way
# migration 0030 stores global_markup_pct: a row in the generic app_setting
# table, seeded by migrations/0047_exchange_sources.sql at 2000 -- today's
# real value (no USD_IRT_FLAT_MARKUP env var is set in production), so
# applying that migration is a strict no-op on every displayed and billed
# price.
#
# Mirrors content.py's get_global_markup_pct() cache-then-DB shape, with one
# deliberate difference in fail-open direction: get_global_markup_pct()
# fails open to 0 because 0 IS today's real (seeded) value for THAT
# setting. Here, today's real value is 2000, not 0 -- so this fails open to
# content.USD_IRT_FLAT_MARKUP, never to 0. Failing to 0 would silently
# strip the entire flat margin off every price on a Redis/DB hiccup, which
# is the wrong direction under the house rule that no request may ever be
# loss-making.
FLAT_MARKUP_SETTING_KEY = 'usd_irt_flat_markup_toman'
FLAT_MARKUP_CACHE_KEY = 'cache:markup:usd_irt_flat_toman'
FLAT_MARKUP_CACHE_TTL = 300  # admin writes also delete this key immediately (exchange_rate_admin.py)


async def get_flat_markup_toman() -> float:
    """Redis-cached flat Toman markup on the USD->IRT rate. Degrades to
    content.USD_IRT_FLAT_MARKUP -- never 0 -- on any cache-read failure,
    missing row, or DB error; see the section comment above for why that
    direction matters. Wraps each stage in its own try/except (rather than
    one big block) so a cache read that returns a wrong-shaped value (a
    dict instead of a bare number -- this happens in tests that blanket-mock
    rds.get for a different key) degrades to the DB read instead of
    propagating, exactly like get_global_markup_pct()."""
    try:
        cached = await rds.get(FLAT_MARKUP_CACHE_KEY)
        if cached is not None:
            return float(json.loads(cached))
    except Exception as e:
        logger.warning('flat markup cache read failed: %s', e)

    value = content.USD_IRT_FLAT_MARKUP
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    'SELECT value FROM app_setting WHERE key = :k'
                ), {'k': FLAT_MARKUP_SETTING_KEY})
                row = res.fetchone()
                if row is not None and row.value is not None:
                    value = float(row.value)
    except Exception as e:
        logger.warning('flat markup DB read failed: %s', e)
        return content.USD_IRT_FLAT_MARKUP

    try:
        await rds.setex(FLAT_MARKUP_CACHE_KEY, FLAT_MARKUP_CACHE_TTL, json.dumps(value))
    except Exception as e:
        logger.warning('flat markup cache write failed: %s', e)

    return value


def _apply_unit(raw: float, unit: str) -> float:
    """Bonbast and most other sites publish Toman directly; tgju-style
    sites publish Rial (divide by 10). `unit` is admin-chosen per source at
    write time -- see exchange_rate_admin.py's validation."""
    return raw / 10.0 if unit == 'rial' else raw


# ── Bounded regex extraction (custom_regex sources) ─────────────────────
_MAX_EXTRACT_TEXT_BYTES = 4096  # capped BEFORE matching -- bounds worst-case match time even for a pathological pattern
_REGEX_TIMEOUT_S = 1.0
_MAX_REGEX_PATTERN_LEN = 200  # mirrors the DB CHECK constraint in migrations/0047


class _RegexTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _RegexTimeout()


def _bounded_search(pattern: str, text: str):
    """re.search with a hard wall-clock budget (SIGALRM) and a length cap
    on the haystack -- an admin-supplied pattern can never hang or stall
    the request path. Signal-based timers only fire on the main thread;
    this is called from `async def` code running directly on the event
    loop (no thread offload), which in this codebase's uvicorn deployment
    is the main thread, so the alarm always applies. If it is ever called
    off the main thread (signal.signal raises ValueError there), this
    degrades to an unbounded-but-still-length-capped search rather than
    crash the caller.
    """
    capped = (text or '')[:_MAX_EXTRACT_TEXT_BYTES]
    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    except ValueError:
        return re.search(pattern, capped)
    try:
        signal.setitimer(signal.ITIMER_REAL, _REGEX_TIMEOUT_S)
        try:
            return re.search(pattern, capped)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    except _RegexTimeout:
        logger.warning('exchange source regex extraction timed out (>%ss)', _REGEX_TIMEOUT_S)
        return None
    finally:
        signal.signal(signal.SIGALRM, old_handler)


# Common catastrophic-backtracking shapes: a quantified group directly
# containing another quantifier (e.g. (.*)+, (a+)+, (\d*)*). This is a
# heuristic rejection at WRITE time only -- it catches the textbook cases,
# it does not prove a pattern is safe. _bounded_search()'s length cap +
# wall-clock timeout above is the real backstop every pattern goes through
# at FETCH time regardless of whether it passed this check.
_NESTED_QUANTIFIER_RE = re.compile(r'\([^()]*[+*][^()]*\)[+*]')


def validate_custom_regex_pattern(pattern: str) -> tuple[str, str] | None:
    """`(persian, english)` describing why `pattern` is rejected, or None.

    Returns the pair rather than one language for the same reason the rest of
    this backend does (backend/i18n.py): the caller turns it straight into a
    response body carrying both, so nothing here has to know who is asking.
    Callers that only test truthiness are unaffected by the change of shape.
    """
    if not pattern or not pattern.strip():
        return ('الگوی استخراج الزامی است',
                'An extraction pattern is required.')
    if len(pattern) > _MAX_REGEX_PATTERN_LEN:
        return (f'الگوی استخراج بیش از حد بلند است (حداکثر {_MAX_REGEX_PATTERN_LEN} نویسه)',
                f'The extraction pattern is too long (max {_MAX_REGEX_PATTERN_LEN} characters).')
    if _NESTED_QUANTIFIER_RE.search(pattern):
        return ('الگوی استخراج شامل تکرار تودرتو است که می‌تواند سرور را کند کند (مثل (.*)+)',
                'The extraction pattern contains nested repetition, which can stall '
                'the server (for example (.*)+).')
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return (f'الگوی استخراج نامعتبر است: {e}',
                f'The extraction pattern is not valid: {e}')
    if compiled.groups < 1:
        return ('الگوی استخراج باید دست‌کم یک گروه () برای عدد نرخ داشته باشد',
                'The extraction pattern needs at least one () group to capture the rate.')
    return None


# ── URL validation (best-effort SSRF guard, write time) ──────────────────
_BLOCKED_HOSTNAMES = {
    'localhost', 'localhost.localdomain',
    'sanjabai_pg', 'sanjabai_redis', 'sanjabai_litellm', 'sanjabai_api',
    'sanjabai_frontend', 'sanjabai_bot', 'sanjabai_tunnel',
    'sanjabai-sanjabai_pg-1', 'sanjabai-sanjabai_redis-1',
    'sanjabai-sanjabai_litellm-1', 'sanjabai-sanjabai_api-1',
    'sanjabai-sanjabai_frontend-1', 'sanjabai-sanjabai_bot-1',
}


def validate_source_url(url: str) -> tuple[str, str] | None:
    """`(persian, english)` describing why `url` is rejected, or None.
    Best-effort only -- see the module docstring's Trust boundary section
    for what this does and does not defend against."""
    if not url or len(url) > 2048:
        return ('نشانی نامعتبر یا بیش از حد بلند است',
                'The URL is invalid or too long.')
    try:
        parsed = urlparse(url)
    except ValueError:
        return ('نشانی قابل تجزیه نیست', 'The URL could not be parsed.')
    if parsed.scheme != 'https':
        return ('فقط نشانی https مجاز است', 'Only https URLs are allowed.')
    host = (parsed.hostname or '').lower()
    if not host:
        return ('نشانی بدون میزبان معتبر نیست', 'A URL without a host is not valid.')
    if host in _BLOCKED_HOSTNAMES or host.endswith('.local') or host.endswith('.internal'):
        return ('این نشانی به شبکهٔ داخلی سرور اشاره دارد و مجاز نیست',
                'This URL points at the server\'s internal network and is not allowed.')
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local
                            or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
        return ('آدرس IP داخلی/خصوصی مجاز نیست',
                'Internal or private IP addresses are not allowed.')
    return None


# ── Bonbast.com fetcher ───────────────────────────────────────────────────
# Verified live on 2026-08-25: a bare GET/POST without the headers below
# gets `{"reset":"1"}` from bonbast.com's own anti-scraping check (its
# client-side JS reloads the page when it sees that). The working sequence,
# confirmed against the live site:
#   1. GET https://bonbast.com/ -- picks up the `st_bb` cookie and a
#      per-page-load POST token embedded in the page's own inline script
#      ($.post('/json', {param: "<token>"}, ...)).
#   2. POST https://bonbast.com/json with that token as form field `param`,
#      the same cookie (content._http is a single shared, long-lived
#      httpx.AsyncClient, so its cookie jar carries the `st_bb` cookie from
#      step 1 into step 2 automatically), and browser-shaped headers
#      (Referer, Origin, Accept, X-Requested-With) -- omitting any of these
#      four also produced {"reset":"1"} in testing.
# The JSON response's "usd1" key is Toman, not Rial -- the page's own
# markup confirms this (`<span id="usd1_top"></span> <sup>Toman</sup>`
# next to the USD row), and the live value (203,700) matches Iran's actual
# free-market USD rate order of magnitude on this date, not a 10x-off
# Rial figure. No /10 conversion here, unlike tgju.
_BONBAST_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
_BONBAST_TOKEN_RE = re.compile(r"""post\(\s*['"]/json['"]\s*,\s*\{\s*param:\s*["']([^"']{1,200})["']""")
_BONBAST_PAGE_MAX_BYTES = 1_000_000  # 1MB cap; live page is ~43KB (verified 2026-08-25)


async def _fetch_bonbast_rate() -> float | None:
    try:
        page = await content._http.get(
            'https://bonbast.com/',
            headers={'User-Agent': _BONBAST_UA},
            follow_redirects=True,
            timeout=content.TGJU_TIMEOUT_S,
        )
        page.raise_for_status()
        # The live page is ~43KB (verified 2026-08-25) with the token near
        # the very end of the file, well past a few KB -- unlike the
        # admin-supplied custom_regex path, this fetcher's own regex is
        # fixed (not attacker-controlled), so a larger cap here is safe; it
        # exists only to bound memory/time against a compromised or
        # malicious bonbast.com serving an unbounded response.
        text = (page.text or '')[:_BONBAST_PAGE_MAX_BYTES]
        m = _BONBAST_TOKEN_RE.search(text)
        if not m:
            return None
        token = m.group(1)

        resp = await content._http.post(
            'https://bonbast.com/json',
            headers={
                'User-Agent': _BONBAST_UA,
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': 'https://bonbast.com/',
                'Origin': 'https://bonbast.com',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
            },
            data={'param': token},
            follow_redirects=False,
            timeout=content.TGJU_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or 'reset' in data or 'usd1' not in data:
            return None
        return float(str(data['usd1']).replace(',', '').strip())
    except Exception as e:
        logger.warning('bonbast USD rate fetch failed: %s', e)
    return None


# ── Generic declarative fetcher (admin-added custom_regex sources) ───────
async def _fetch_custom_regex_rate(row: Any) -> float | None:
    """`row` has .source_key, .url, .extract_regex, .unit, .timeout_s (a
    fetchall() row from exchange_rate_sources). One GET, one bounded regex,
    no code execution -- see the module docstring's Trust boundary."""
    try:
        timeout = min(float(row.timeout_s or 5), 10.0)
        resp = await content._http.get(
            row.url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; SanjabaiExchangeRateBot/1.0)'},
            follow_redirects=False,  # a same-URL redirect to an internal host is a classic SSRF bypass; refuse to chase it
            timeout=timeout,
        )
        resp.raise_for_status()
        m = _bounded_search(row.extract_regex, resp.text)
        if not m:
            return None
        raw = m.group(1) if m.groups() else m.group(0)
        raw_num = float(str(raw).replace(',', '').strip())
        return _apply_unit(raw_num, row.unit)
    except Exception as e:
        logger.warning('custom exchange source %s fetch failed: %s', getattr(row, 'source_key', '?'), e)
    return None


# Safety cap on how many admin-added rows one resolution pass will try, so
# a long list of slow/misconfigured custom sources can never stack up an
# unbounded amount of latency on a cache-miss request (each row is already
# individually capped to <=10s by the DB CHECK constraint + the min() above).
_MAX_ROWS_TRIED = 8


async def resolve_configured_sources() -> tuple[float | None, str | None]:
    """Walk enabled exchange_rate_sources rows in priority order (lowest
    first), dispatching by `kind`. Returns the first candidate that both
    fetches successfully and passes is_plausible_usd_irt_toman(), else
    (None, None). Every row's failure -- network error, bad parse, an
    implausible number -- is caught here and just skips to the next row;
    this function must never raise and never return an unvalidated rate.
    """
    if not async_session:
        return None, None
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                'SELECT source_key, display_name, kind, url, unit, extract_regex, timeout_s '
                'FROM exchange_rate_sources WHERE enabled = TRUE ORDER BY priority ASC, id ASC'
            ))
            rows = res.fetchall()
    except Exception as e:
        logger.warning('exchange_rate_sources read failed: %s', e)
        return None, None

    for row in rows[:_MAX_ROWS_TRIED]:
        try:
            if row.kind == 'bonbast':
                rate = await _fetch_bonbast_rate()
            elif row.kind == 'custom_regex':
                rate = await _fetch_custom_regex_rate(row)
            else:
                logger.warning('exchange_rate_sources: unknown kind %r for %r, skipping', row.kind, row.source_key)
                continue
        except Exception as e:
            logger.warning('exchange source %s raised unexpectedly: %s', row.source_key, e)
            continue

        if rate is None:
            continue
        if not is_plausible_usd_irt_toman(rate):
            logger.warning('exchange source %s returned an implausible rate %r Toman, rejecting', row.source_key, rate)
            continue
        return rate, row.source_key

    return None, None
