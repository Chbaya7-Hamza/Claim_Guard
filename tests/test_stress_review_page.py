"""The offline review page shows claim data an attacker chose. It must show it as text, never run it."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from make_review import build

HOSTILE = [
    '</script><img src=x onerror=alert(1)>',
    '<script>alert(document.cookie)</script>',
    '<!-- <script>',
    '"><svg/onload=alert(1)>',
    "'; alert(1); //",
    '&lt;b&gt; &amp; &#x3C;script&#x3E;',
    '  ',
    '${alert(1)} `x`',
]


def row(text, i):
    return {'claim_id': f'CG-{i}', 'rule_id': 'R001', 'rule_version': '1.0.0', 'status': 'FAIL', 'severity': 'high',
            'affected_line_ids': [], 'evidence': [{'path': '/notes', 'value': text}], 'rule_source': text,
            'explanation': text, 'corrective_action': text, 'confidence': None, 'confidence_kind': 'not_probabilistic',
            'requires_human_review': True, 'method': 'deterministic', 'review_status': 'unreviewed'}


class ReviewPageIsInert(unittest.TestCase):
    def setUp(self):
        self.rows = [row(t, i) for i, t in enumerate(HOSTILE)]
        self.page = build(self.rows)

    def test_the_only_script_block_is_ours_and_nothing_else_becomes_markup(self):
        self.assertEqual(self.page.count('</script>'), 1)
        self.assertEqual(self.page.count('<script'), 1)
        # 'onerror=' may appear inside a JSON string (inert data); only a raw '<' could start markup
        for needle in ('<img', '<svg', '<!--', '<b>'):
            self.assertNotIn(needle, self.page.replace('<!doctype', ''), needle)

    def test_the_embedded_data_round_trips_exactly(self):
        start = self.page.index('const rows=') + len('const rows=')
        end = self.page.index(', decisions=[]')
        self.assertEqual(json.loads(self.page[start:end]), self.rows)

    def test_the_page_script_never_writes_markup(self):
        for sink in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function', 'setTimeout("'):
            self.assertNotIn(sink, self.page, sink)
        self.assertRegex(self.page, r'textContent=text')

    def test_a_result_text_containing_the_placeholder_word_does_not_corrupt_the_page(self):
        page = build([row('DATA DATA DATA', 1)])
        start = page.index('const rows=') + len('const rows=')
        end = page.index(', decisions=[]')
        self.assertEqual(json.loads(page[start:end])[0]['explanation'], 'DATA DATA DATA')

    def test_nine_thousand_results_still_build_a_page_a_browser_can_open(self):
        page = build([row('x', i) for i in range(9000)])
        self.assertLess(len(page), 12_000_000)
        self.assertEqual(len(re.findall(r'"claim_id"', page)), 9000)


if __name__ == '__main__':
    unittest.main()
