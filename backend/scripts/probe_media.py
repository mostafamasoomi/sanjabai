#!/usr/bin/env python3
"""Probe the upstreams' image/video endpoints and record what they answer.

Why this is a committed script and not a throwaway shell one-liner: the
product rule is that no model is offered to a user until a live probe has
confirmed it works, and as of 2026-08-22 *no* media probe succeeds -- every
image provider the upstreams register is either uncredentialed or out of
credit, and no video provider is credentialed at all. So the response shape
of a *successful* generation is still unknown, and writing a parser against
a guessed shape would be exactly the kind of unverified claim the honest-
labelling rule exists to prevent.

The moment the owner adds a provider key, running this script answers the
three questions the media endpoint has to be built against:

  * what does a success envelope look like -- a URL, base64, or a job id
    that has to be polled?
  * how long does it take? (an image took 103s on the one route that got as
    far as the provider, so no timeout below that is safe)
  * how many billable units come back for one request?

Read-only. It never writes to the database and never changes a model's
availability.

Usage:
    python scripts/probe_media.py --mode discover
    python scripts/probe_media.py --mode images --model pollinations/flux
    python scripts/probe_media.py --mode video  --model xai/grok-video
    python scripts/probe_media.py --mode images --model pollinations/flux \
        --report /root/media_probe.json

The key comes from NINEROUTER_API_KEY (or --api-key). The upstream base URLs
come from NINEROUTER_URL / OMNIROUTER_URL, matching what the app itself uses.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# 9Router legitimately takes up to ~11s just to answer GET /v1/models, and a
# real image generation took 103s on the one route that reached a provider.
# Nothing here may use a short timeout -- a probe that times out early gets
# recorded as a failure and would park a model that actually works.
DISCOVER_TIMEOUT = 30
IMAGE_TIMEOUT = 300
VIDEO_TIMEOUT = 900

#: Providers each upstream was observed to register, 2026-08-22. Used by
#: --mode discover to re-check the credential state of each one cheaply.
KNOWN_IMAGE_PROVIDERS = [
    'openrouter', 'antigravity', 'openai', 'black-forest-labs',
    'together', 'nvidia', 'pollinations',
]
KNOWN_VIDEO_PROVIDERS = ['xai']


def _upstreams(args):
    out = []
    nine = args.ninerouter_url or os.getenv('NINEROUTER_URL')
    omni = args.omniroute_url or os.getenv('OMNIROUTER_URL')
    if nine:
        out.append(('ninerouter', nine.rstrip('/')))
    if omni:
        out.append(('omniroute', omni.rstrip('/')))
    return out


def _summarise(obj):
    """Describe big blobs instead of printing them.

    A base64 image is megabytes; dumping it would bury the shape we are
    actually here to learn. The length and prefix are kept because they are
    what tells a data URL apart from a signed URL apart from raw base64.
    """
    if isinstance(obj, str):
        if len(obj) > 300:
            return f'<{len(obj)} chars, starts: {obj[:80]!r}>'
        return obj
    if isinstance(obj, dict):
        return {k: _summarise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        head = [_summarise(v) for v in obj[:3]]
        return head + ([f'<+{len(obj) - 3} more>'] if len(obj) > 3 else [])
    return obj


def call(base, path, body, key, timeout):
    req = urllib.request.Request(
        f'{base}{path}', data=json.dumps(body).encode(),
        headers={'Authorization': f'Bearer {key}',
                 'Content-Type': 'application/json'})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, code = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    except Exception as e:                          # noqa: BLE001
        return {'error': f'{type(e).__name__}: {e}',
                'seconds': round(time.monotonic() - started, 1)}
    result = {'http': code, 'bytes': len(raw),
              'seconds': round(time.monotonic() - started, 1)}
    try:
        result['body'] = _summarise(json.loads(raw))
    except ValueError:
        result['body_raw'] = raw[:300].decode('utf-8', 'replace')
    return result


def discover(upstreams, key):
    """Ask each upstream which media providers it has credentials for.

    Sends a deliberately nonexistent model so nothing is ever generated and
    nothing is ever billed -- the useful signal is entirely in which error
    comes back. Three distinct answers matter: an unknown-provider error
    means the upstream does not route to it at all, a no-credentials error
    means it would work with a key, and anything else means the request
    reached the provider and the provider itself answered.
    """
    out = {}
    for name, base in upstreams:
        out[name] = {'images': {}, 'video': {}}
        for prov in KNOWN_IMAGE_PROVIDERS:
            out[name]['images'][prov] = call(
                base, '/v1/images/generations',
                {'model': f'{prov}/probe-nonexistent-model', 'prompt': 'x'},
                key, DISCOVER_TIMEOUT)
        for prov in KNOWN_VIDEO_PROVIDERS:
            out[name]['video'][prov] = call(
                base, '/v1/videos/generations',
                {'model': f'{prov}/probe-nonexistent-model', 'prompt': 'x'},
                key, DISCOVER_TIMEOUT)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', required=True,
                    choices=['discover', 'images', 'video'])
    ap.add_argument('--model', help='provider/model, e.g. pollinations/flux')
    ap.add_argument('--prompt', default='a single red apple on a white background')
    ap.add_argument('--seconds', type=int, default=4, help='video length')
    ap.add_argument('--api-key', default=os.getenv('NINEROUTER_API_KEY'))
    ap.add_argument('--ninerouter-url')
    ap.add_argument('--omniroute-url')
    ap.add_argument('--report', help='also write the raw result here as JSON')
    args = ap.parse_args()

    if not args.api_key:
        sys.exit('no API key: pass --api-key or set NINEROUTER_API_KEY')
    upstreams = _upstreams(args)
    if not upstreams:
        sys.exit('no upstream URLs: set NINEROUTER_URL / OMNIROUTER_URL')

    if args.mode == 'discover':
        result = discover(upstreams, args.api_key)
    else:
        if not args.model:
            sys.exit('--model is required for --mode images/video')
        if args.mode == 'images':
            path, body, timeout = ('/v1/images/generations',
                                   {'model': args.model, 'prompt': args.prompt,
                                    'n': 1}, IMAGE_TIMEOUT)
        else:
            path, body, timeout = ('/v1/videos/generations',
                                   {'model': args.model, 'prompt': args.prompt,
                                    'seconds': args.seconds}, VIDEO_TIMEOUT)
        result = {name: call(base, path, body, args.api_key, timeout)
                  for name, base in upstreams}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f'\nwrote {args.report}', file=sys.stderr)


if __name__ == '__main__':
    main()
