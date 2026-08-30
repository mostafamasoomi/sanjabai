"""Regression test for the usage-echo mismatch found live on
sanjab/qwen3.8-27b: the upstream can inject a phantom preamble into
`usage.prompt_tokens` (e.g. 2206) that `_record_usage` correctly discounts
before charging (e.g. input_tokens=316) -- billing was never wrong, only
the raw, inflated `usage` object was echoed back to the client unchanged.

`chat_billing._reconcile_usage` is a pure function (no DB, no `chat`
module dependency) that overwrites the client-visible `usage` block with
the actually-billed `cost_info` counts. Tested directly here, plus a
wiring guard proving `_track_usage` actually calls it (a fix that isn't
called from anywhere is not a fix).
"""
from __future__ import annotations

import inspect

import chat_billing


def test_reconcile_usage_overwrites_with_billed_counts():
    response_data = {
        'usage': {
            'prompt_tokens': 2206,
            'completion_tokens': 79,
            'total_tokens': 2285,
        }
    }
    cost_info = {'input_tokens': 316, 'output_tokens': 79}

    chat_billing._reconcile_usage(response_data, cost_info)

    usage = response_data['usage']
    assert usage['prompt_tokens'] == 316
    assert usage['completion_tokens'] == 79
    assert usage['total_tokens'] == 395


def test_reconcile_usage_noop_when_no_usage_key():
    response_data = {'id': 'chatcmpl-abc', 'choices': []}
    cost_info = {'input_tokens': 316, 'output_tokens': 79}

    # Must not raise, and must not fabricate a usage block.
    chat_billing._reconcile_usage(response_data, cost_info)

    assert 'usage' not in response_data


def test_reconcile_usage_noop_on_malformed_shapes():
    # usage present but not a dict
    rd = {'usage': 'not-a-dict'}
    chat_billing._reconcile_usage(rd, {'input_tokens': 1, 'output_tokens': 1})
    assert rd['usage'] == 'not-a-dict'

    # cost_info missing the expected keys
    rd2 = {'usage': {'prompt_tokens': 100}}
    chat_billing._reconcile_usage(rd2, {})
    assert rd2['usage'] == {'prompt_tokens': 100}

    # response_data itself not a dict -- must not raise
    chat_billing._reconcile_usage(None, {'input_tokens': 1, 'output_tokens': 1})
    chat_billing._reconcile_usage([], {'input_tokens': 1, 'output_tokens': 1})


def test_track_usage_calls_reconcile_usage():
    """Wiring guard: a helper nothing calls is not a fix. Read the real
    source of `_track_usage` and assert it invokes `_reconcile_usage` --
    this goes red if the call site is ever removed or refactored away,
    independent of any mocking of chat.async_session.
    """
    src = inspect.getsource(chat_billing._track_usage)
    assert '_reconcile_usage(' in src
