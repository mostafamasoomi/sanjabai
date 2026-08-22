"""
Tests for model_output.py's pure text-cleaning helpers.

Fixtures use the REAL strings observed live (see model_output.py's module
docstring and chat.py's FIX 1 comments): 9Router-routed models leak their
chain-of-thought inline in the visible answer via <thought>/<think> tags,
sometimes truncated (max_tokens cut them off mid-thought), sometimes with
the opening tag already eaten by the upstream.
"""
from __future__ import annotations

import pytest

from model_output import (
    ReasoningStreamFilter,
    clean_response_dict,
    strip_reasoning,
)


class TestStripReasoningPassthrough:
    def test_clean_text_is_byte_identical(self):
        text = 'ماشین یادگیری الگو از داده‌ها. الگوریتم تصمیم می‌گیرد برای حل مسئله.'
        # Must be the exact same object back -- true passthrough, not a
        # stripped/reformatted copy that merely compares equal.
        assert strip_reasoning(text) is text

    def test_empty_string_passthrough(self):
        assert strip_reasoning('') == ''

    def test_non_string_passthrough(self):
        assert strip_reasoning(None) is None
        assert strip_reasoning(42) == 42


class TestStripReasoningCompletePair:
    def test_whole_content_is_only_a_thought_block(self):
        # The real observed sanjab/gemma-4-26b-a4b-it answer to "hi".
        assert strip_reasoning('<thought>*   </thought>') == ''

    def test_pair_surrounded_by_real_text(self):
        text = 'قبل از فکر <thought>یک فکر مخفی اینجاست</thought> بعد از فکر'
        result = strip_reasoning(text)
        assert 'thought' not in result.lower()
        assert 'فکر مخفی' not in result
        assert result.startswith('قبل از فکر')
        assert result.endswith('بعد از فکر')

    def test_think_tag_variant(self):
        assert strip_reasoning('<think>reasoning here</think>پاسخ نهایی') == 'پاسخ نهایی'

    def test_case_insensitive_tags(self):
        assert strip_reasoning('<THOUGHT>x</THOUGHT>پاسخ') == 'پاسخ'
        assert strip_reasoning('<Thought>x</ThoUGHt>پاسخ') == 'پاسخ'

    def test_multiple_pairs_both_removed(self):
        text = '<thought>a</thought>سلام<thought>b</thought>خداحافظ'
        assert strip_reasoning(text) == 'سلامخداحافظ'

    def test_leading_trailing_whitespace_tidied_when_tag_present(self):
        text = '  <thought>x</thought>  پاسخ  '
        assert strip_reasoning(text) == 'پاسخ'


class TestStripReasoningUnclosedOpen:
    def test_unclosed_tag_with_no_prefix_yields_empty(self):
        # Real shape: model ran out of tokens mid-thought, no closing tag
        # ever arrives.
        text = '<thought>*   User request: explain the request in Persian...'
        assert strip_reasoning(text) == ''

    def test_unclosed_tag_drops_everything_from_tag_to_end_keeps_prefix(self):
        text = 'سلام <thought>در حال فکر کردن هستم و هرگز تمام نمی‌شود'
        assert strip_reasoning(text) == 'سلام'


class TestStripReasoningStrayClose:
    def test_stray_closing_tag_drops_everything_before_it(self):
        # Upstream already ate the opening tag; only the close leaks through.
        text = 'باقیمانده فکر پنهان</thought>این پاسخ واقعی است'
        assert strip_reasoning(text) == 'این پاسخ واقعی است'

    def test_stray_closing_tag_think_variant(self):
        text = 'leaked reasoning fragment</think>real answer'
        assert strip_reasoning(text) == 'real answer'


class TestCleanResponseDict:
    def test_cleans_every_choice(self):
        data = {
            'choices': [
                {'message': {'content': '<thought>x</thought>پاسخ یک'}},
                {'message': {'content': 'پاسخ دو بدون فکر'}},
            ]
        }
        out = clean_response_dict(data)
        assert out is data
        assert data['choices'][0]['message']['content'] == 'پاسخ یک'
        assert data['choices'][1]['message']['content'] == 'پاسخ دو بدون فکر'

    def test_tolerates_malformed_body(self):
        assert clean_response_dict({}) == {}
        assert clean_response_dict({'choices': 'not-a-list'}) == {'choices': 'not-a-list'}
        assert clean_response_dict({'choices': [{'message': 'not-a-dict'}]}) == {
            'choices': [{'message': 'not-a-dict'}]
        }
        assert clean_response_dict({'choices': [{'message': {'content': None}}]}) == {
            'choices': [{'message': {'content': None}}]
        }
        assert clean_response_dict(None) is None


class TestReasoningStreamFilter:
    def _run_streaming(self, text: str) -> str:
        f = ReasoningStreamFilter()
        out = []
        for ch in text:
            out.append(f.feed(ch))
        out.append(f.flush())
        return ''.join(out)

    @pytest.mark.parametrize('text', [
        'پاسخ کاملا تمیز بدون هیچ برچسبی',
        'سلام <thought>fkjdslkfj\nsome reasoning</thought> پاسخ نهایی',
        '<thought>*   </thought>',
        '<think>x</think>پاسخ',
        'قبل<thought>a</thought>وسط<thought>b</thought>بعد',
        '<THOUGHT>x</THOUGHT>پاسخ بزرگ حروف',
    ])
    def test_streaming_matches_non_streaming_char_by_char(self, text):
        assert self._run_streaming(text) == strip_reasoning(text)

    def test_streaming_unclosed_tag_at_stream_end_is_discarded(self):
        # The trailing space before the tag was already emitted by the time
        # the tag opens, so unlike strip_reasoning() (which sees the whole
        # string at once and can .strip() it) the streaming filter cannot
        # retroactively tidy it without buffering already-sent text -- that
        # one whitespace character is the documented, deliberate difference.
        text = 'سلام <thought>هرگز تمام نمی‌شود'
        assert self._run_streaming(text).strip() == strip_reasoning(text) == 'سلام'

    def test_feed_in_arbitrary_chunk_boundaries_not_just_one_char(self):
        # Same content as the per-character test above, but split into a
        # few larger, tag-boundary-crossing chunks -- proves feed() isn't
        # only correct when called one character at a time.
        chunks = ['سلام <tho', 'ught>some reason', 'ing</though', 't> پاسخ']
        f = ReasoningStreamFilter()
        out = ''.join(f.feed(c) for c in chunks) + f.flush()
        assert out == strip_reasoning(''.join(chunks))

    def test_plain_text_has_no_added_latency_emitted_immediately(self):
        f = ReasoningStreamFilter()
        assert f.feed('hello ') == 'hello '
        assert f.feed('world') == 'world'
        assert f.flush() == ''

    def test_angle_bracket_not_our_tag_passes_through(self):
        text = 'a<b>bold-ish</b>c'
        assert self._run_streaming(text) == strip_reasoning(text) == text
