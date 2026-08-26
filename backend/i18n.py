"""
Bilingual responses.

THE DECISION THIS FILE ENCODES: a response carries BOTH languages, always.
It does not carry the one the caller asked for.

The obvious alternative -- read ``Accept-Language`` and answer in that
language -- is wrong here, and expensively so. Seventeen payloads in this
backend are cached in Redis under a fixed key: ``cache:catalog:models``,
``cache:catalog:pricing``, ``cache:api:pricing``, ``cache:content:features``,
``cache:model_health:summary``, and the rest. The moment a response depends on
a request header, every one of those keys needs a language suffix, and every
key that anyone forgets serves the wrong language to somebody -- silently, for
up to the cache TTL, with nothing in a log to say it happened. That is a large
failure surface bought for nothing: the payloads are small, and shipping both
languages in one body costs a few hundred bytes and keeps the cache exactly as
it is.

So:

  errors    {"detail": "<fa>", "detail_en": "<en>"}
  /v1/*     {"error": {"message": "<fa>", "message_en": "<en>", "type", "code"}}
  payloads  {"label": "<fa>", "label_en": "<en>"}

The Persian key keeps its existing name and its existing value in every case.
That is deliberate -- every current consumer, including the Telegram bot and
anything reading these endpoints outside this repo, keeps working untouched,
and an English-speaking client opts in by reading the ``_en`` sibling. A
missing ``_en`` degrades to Persian rather than to an empty string.

There is no ``raise HTTPException`` idiom in this codebase; endpoints return
``JSONResponse({'detail': ...}, status_code=...)`` directly (912 call sites).
``err()`` below is that same shape with the English sibling filled in, so
converting a site is a one-line edit and never changes its status code or its
Persian text.
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

# The two languages the product ships. Kept as a constant so a third one is a
# single edit here plus the dictionaries, not a search for string literals.
LANGS = ('fa', 'en')


def err(fa: str, en: str, status: int) -> JSONResponse:
    """A refusal, in both languages.

    ``fa`` stays under ``detail`` exactly as it was, so nothing that reads
    that key today notices this change.

        return err('کپچا اشتباه است', 'Incorrect captcha', 400)
    """
    return JSONResponse({'detail': fa, 'detail_en': en}, status_code=status)


def err_openai(
    fa: str,
    en: str,
    status: int,
    *,
    code: str | None = None,
    err_type: str = 'invalid_request',
) -> JSONResponse:
    """A refusal in the OpenAI-compatible shape, in both languages.

    The `/v1/*` routes do not answer with `detail`; they answer with
    ``{"error": {"message", "type", "code"}}`` because OpenAI-compatible
    clients branch on `type` and `code`. Those two fields are contract and are
    passed through untouched -- only the human sentence gains a sibling.

    This exists because the chat and image paths had no sanctioned way to be
    bilingual: `err()` would have flattened them to `detail` and silently
    dropped `code`, changing the contract for every SDK pointed at this API.
    The frontend already reads `error.message_en` (lib/i18n.ts::detailFor).
    """
    body: dict[str, Any] = {'message': fa, 'message_en': en, 'type': err_type}
    if code is not None:
        body['code'] = code
    return JSONResponse({'error': body}, status_code=status)


def bi(payload: dict[str, Any], **pairs: tuple[str, str]) -> dict[str, Any]:
    """Add ``_en`` siblings to a payload.

        return bi({'id': flag.key}, label=(flag.label_fa, flag.label_en))
        # -> {'id': ..., 'label': '<fa>', 'label_en': '<en>'}

    Written as a helper rather than by hand at each site so the sibling key is
    always ``<name>_en`` and never ``<name>En`` or ``en_<name>``; the frontend
    reads one convention.
    """
    for name, (fa, en) in pairs.items():
        payload[name] = fa
        payload[f'{name}_en'] = en
    return payload


def pick(row: Any, name: str, lang: str = 'fa') -> str:
    """The ``name_fa`` / ``name_en`` pair off a DB row, for the rare caller
    that must collapse to one language server-side (a Telegram message, an
    email). Falls back to Persian when the English column is null or empty --
    an untranslated row must read as Persian, never as blank.

    Accepts a mapping or an object with attributes, because this codebase
    reads rows both ways.
    """
    def get(key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

    fa = get(f'{name}_fa') or get(name) or ''
    if lang != 'en':
        return str(fa)
    return str(get(f'{name}_en') or fa)
