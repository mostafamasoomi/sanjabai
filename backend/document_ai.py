"""AI content generation for the Document Generator -- split out of
document_generator.py to stay under the house 500-line cap, AND to give
the upstream call a module of its own now that document_generator.py's
handler wraps it in a billing/gating bracket (see document_generator.py's
module docstring for the full incident writeup and the fix).

THE ONE UPSTREAM CALL. :func:`generate_content` is the only place a
document-generation prompt is ever sent to `{LITELLM_HOST}/v1/chat/completions`.
It is deliberately mechanical: it does the HTTP call, its own resilience
retry, and the JSON-shape parsing/capping -- nothing about billing, model
validation, moderation or quotas lives here. document_generator.py's
`/v1/documents/generate` handler is the only caller, and it only ever
calls this function ONCE per request, after every gate (model validation,
chat_enabled, moderation, free-tier, quota) has already passed and a
wallet reservation is already open.

WHY THE INTERNAL RETRY CANNOT DOUBLE-CHARGE. The `for attempt in range(2)`
loop below may hit the upstream twice (once with `model`, once with
`fallback_model`, on a timeout/5xx/transport error), but it returns
EXACTLY ONCE -- either the (data, usage, model_used) triple for whichever
attempt actually succeeded, or it raises after both attempts are
exhausted. document_generator.py bills exactly once, after this function
returns successfully, using the returned `model_used`/`usage` pair -- so
there is structurally only ever one billing call per HTTP request,
regardless of how many upstream attempts happened inside it.

`fallback_model` is supplied by the caller, already catalog-resolved and
availability-checked (document_generator.py's `_resolve_fallback_model`)
-- this module never forwards an unverified model name upstream on its
own initiative. Passing `None` disables the model-switch on retry (the
loop still retries the SAME model once, preserving the original
resilience-against-a-transient-error behaviour) rather than falling back
to a hardcoded literal, which is what let an unresolved model id miss
`_record_usage`'s price lookup in the original code.

MONKEYPATCH CONTRACT. This module owns its own `_http` (the same shared
`database._HttpProxy` singleton every other module uses, imported here at
module scope) and its own `LITELLM_HOST`. There is no existing shared
monkeypatch contract this module needs to fit into (unlike the chat_*.py
family's `chat.<name>` convention) -- tests patch them directly as
`document_ai._http` / `document_ai.LITELLM_HOST`. A plain global lookup
(`_http.post(...)` below) is resolved against THIS module's namespace at
call time, so `patch.object(document_ai, '_http', fake_http)` is observed
correctly with no extra indirection needed.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from database import _http, LITELLM_HOST

logger = logging.getLogger(__name__)

# Cap unbounded lists to avoid memory/CPU exhaustion (DoS) -- unchanged
# from the pre-split code.
MAX_SLIDES = 30
MAX_SECTIONS = 30

# Tried once, as a resilience fallback, if the first attempt fails --
# document_generator.py resolves/validates this against the live catalog
# before ever passing it in (see `_resolve_fallback_model`); this module
# never uses the literal directly.
FALLBACK_MODEL = 'mimo-v2.5-pro'

_TYPE_INSTRUCTIONS = {
    'pptx': '''Return a JSON object with this exact structure:
{
  "title": "Presentation Title",
  "subtitle": "Optional subtitle",
  "slides": [
    {
      "title": "Slide Title",
      "content": ["Bullet point 1", "Bullet point 2", "Bullet point 3"],
      "notes": "Optional speaker notes"
    }
  ]
}
Create 6-10 slides. Make content professional and detailed.''',

    'docx': '''Return a JSON object with this exact structure:
{
  "title": "Document Title",
  "subtitle": "Optional subtitle",
  "sections": [
    {
      "heading": "Section Heading",
      "content": "Full paragraph content for this section.",
      "subsections": [
        {
          "heading": "Subsection",
          "content": "Subsection content."
        }
      ]
    }
  ]
}
Create 4-8 sections. Make content professional and detailed.''',
}


async def generate_content(
    prompt: str, doc_type: str, model: str, fallback_model: str | None = None,
) -> tuple[dict, dict, str]:
    """Use an AI model to generate structured content for the document.

    Returns ``(data, usage, model_used)``: ``data`` is the parsed/capped
    structured content, ``usage`` is the raw upstream usage block (``{}``
    if the upstream omitted one -- the caller's billing step has its own
    L1 local-estimate fallback for that, same as every other billed path
    in this codebase), and ``model_used`` is whichever of `model` /
    `fallback_model` the successful attempt actually used -- the caller
    bills against THIS, not the originally-requested model, so a
    mid-request fallback still bills the model that was actually called.

    Raises on total failure (both attempts exhausted, or the response body
    is not valid/parseable JSON) -- the caller is responsible for
    releasing its wallet reservation on any exception from here.
    """
    system_msg = f'''You are a professional document/content creator.
Generate structured content for a {doc_type.upper()} document based on the user's request.
{_TYPE_INSTRUCTIONS.get(doc_type, _TYPE_INSTRUCTIONS['pptx'])}

IMPORTANT: Return ONLY valid JSON. No markdown code blocks, no explanations. Just the raw JSON.'''

    # DOCX/PPTX content is long — use a dedicated longer timeout + one retry
    max_tokens = 4096 if doc_type != 'docx' else 3072
    timeout = httpx.Timeout(120.0, connect=15.0)
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': prompt},
        ],
        'stream': False,
        'max_tokens': max_tokens,
    }
    last_err: Exception | None = None
    r = None
    for attempt in range(2):
        try:
            r = await _http.post(
                f'{LITELLM_HOST}/v1/chat/completions',
                json=payload,
                headers={'Accept': 'application/json'},
                timeout=timeout,
            )
            r.raise_for_status()
            break
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError) as e:
            last_err = e
            logger.warning('docgen AI attempt %s failed: %s', attempt + 1, e)
            if attempt == 0:
                # Resilience retry: always retry once. Only SWITCH models if
                # the caller supplied a validated, different fallback --
                # otherwise retry the same (already-validated) model, same
                # as the original single-model behaviour.
                if fallback_model and payload['model'] != fallback_model:
                    payload['model'] = fallback_model
                continue
            raise
    if r is None:
        raise last_err or RuntimeError('document content generation failed')

    resp_data = r.json()
    usage = resp_data.get('usage') or {}
    model_used = payload['model']
    content = resp_data['choices'][0]['message']['content']

    # Try to parse JSON from response — handle markdown code blocks
    content = content.strip()
    if content.startswith('```'):
        # Remove ```json or ``` wrapper
        lines = content.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        content = '\n'.join(lines).strip()

    # Try to find JSON object in the text
    if not content.startswith('{'):
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            content = match.group(0)

    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError('Model returned non-object JSON')

    # Cap unbounded lists to avoid memory/CPU exhaustion (DoS)
    if 'slides' in data:
        data['slides'] = data['slides'][:MAX_SLIDES]
    if 'sections' in data:
        data['sections'] = data['sections'][:MAX_SECTIONS]
    return data, usage, model_used
