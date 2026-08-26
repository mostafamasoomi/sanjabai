"""The bilingual-response contract.

These pin the two properties the rest of the translation work depends on:
the Persian side never moves, and the English side is a predictable sibling
key. If either drifts, 568 converted error sites and every `_en` payload
field drift with it.
"""
import json

import pytest

from i18n import bi, err, pick


class TestErr:
    def test_keeps_the_persian_under_the_original_key(self):
        # The whole backward-compatibility story rests on this: every existing
        # consumer reads `detail`, and must keep reading exactly what it read
        # before the site was converted.
        res = err('کپچا اشتباه است', 'Incorrect captcha', 400)
        body = json.loads(bytes(res.body))
        assert body['detail'] == 'کپچا اشتباه است'
        assert res.status_code == 400

    def test_adds_the_english_as_a_sibling(self):
        res = err('کپچا اشتباه است', 'Incorrect captcha', 400)
        body = json.loads(bytes(res.body))
        assert body['detail_en'] == 'Incorrect captcha'

    def test_carries_nothing_else(self):
        # A refusal body is read by an error path. Extra keys there are how a
        # client starts depending on something we did not mean to promise.
        body = json.loads(bytes(err('الف', 'a', 403).body))
        assert set(body) == {'detail', 'detail_en'}

    @pytest.mark.parametrize('status', [400, 401, 403, 404, 409, 429, 500, 503])
    def test_passes_the_status_through_untouched(self, status):
        assert err('خطا', 'error', status).status_code == status


class TestBi:
    def test_writes_both_keys_and_preserves_the_rest(self):
        out = bi({'id': 'chat'}, label=('گفتگو', 'Chat'))
        assert out == {'id': 'chat', 'label': 'گفتگو', 'label_en': 'Chat'}

    def test_handles_several_pairs_at_once(self):
        out = bi({}, label=('عنوان', 'Title'), description=('توضیح', 'Description'))
        assert out['label'] == 'عنوان' and out['label_en'] == 'Title'
        assert out['description'] == 'توضیح' and out['description_en'] == 'Description'

    def test_suffix_is_exactly_underscore_en(self):
        # One convention. The frontend derives the English key by appending
        # '_en'; camelCase or a prefix would silently read as undefined there.
        assert set(bi({}, title=('الف', 'a'))) == {'title', 'title_en'}


class TestPick:
    def test_persian_by_default(self):
        assert pick({'name_fa': 'سنجاب', 'name_en': 'Squirrel'}, 'name') == 'سنجاب'

    def test_english_when_asked(self):
        assert pick({'name_fa': 'سنجاب', 'name_en': 'Squirrel'}, 'name', 'en') == 'Squirrel'

    def test_untranslated_row_falls_back_to_persian_not_blank(self):
        # 1,200 catalog rows and every hermes offering predate the English
        # columns. An empty English cell must read as the Persian, or asking
        # for English empties the screen.
        assert pick({'name_fa': 'سنجاب', 'name_en': None}, 'name', 'en') == 'سنجاب'
        assert pick({'name_fa': 'سنجاب', 'name_en': ''}, 'name', 'en') == 'سنجاب'

    def test_reads_attributes_as_well_as_mappings(self):
        class Row:
            name_fa = 'سنجاب'
            name_en = 'Squirrel'
        assert pick(Row(), 'name', 'en') == 'Squirrel'
        assert pick(Row(), 'name') == 'سنجاب'

    def test_unsuffixed_column_is_accepted_as_the_persian(self):
        # Several tables spell the Persian column `name`, not `name_fa`.
        assert pick({'name': 'سنجاب'}, 'name', 'en') == 'سنجاب'
