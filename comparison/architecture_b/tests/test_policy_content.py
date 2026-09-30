import re
import sys
import unittest
from pathlib import Path

ADAPTED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADAPTED))


class CstamRulebookContentTests(unittest.TestCase):
    def setUp(self):
        self.text = (ADAPTED / 'policies' / 'cstam_rulebook.txt').read_text(encoding='utf-8')

    def test_all_fifteen_rule_ids_are_present(self):
        for i in range(1, 16):
            with self.subTest(rule=f'R{i:03}'):
                self.assertIn(f'R{i:03}', self.text)

    def test_loader_can_chunk_it(self):
        from document_loader import get_documents
        chunks = get_documents(str(ADAPTED / 'policies'))
        self.assertGreater(len(chunks), 5)


if __name__ == '__main__':
    unittest.main()
