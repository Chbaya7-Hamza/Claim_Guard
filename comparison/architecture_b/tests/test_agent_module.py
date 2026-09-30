import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ADAPTED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADAPTED))


class AgentModuleHasNoImportSideEffectsTests(unittest.TestCase):
    def test_importing_agent_does_not_require_google_api_key_or_load_a_claim(self):
        # If this import raises (missing GOOGLE_API_KEY, missing claim.csv,
        # or tries to hit a real embedding model / FAISS build), the test
        # fails with that exception -- the point of this test is that none
        # of that happens just from `import agent`.
        import agent  # noqa: F401


class BuildRagIndexTests(unittest.TestCase):
    def test_indexes_every_chunk_from_the_policy_directory(self):
        import agent
        rag = agent.build_rag_index(str(ADAPTED / 'policies'))
        self.assertGreater(len(rag.documents), 0)
        self.assertEqual(rag.index.ntotal, len(rag.documents))


class ValidateClaimTests(unittest.TestCase):
    def test_validate_claim_invokes_the_compiled_agent_with_the_claim_text(self):
        import agent

        fake_agent = MagicMock()
        fake_agent.invoke.return_value = {
            'messages': [MagicMock(content='{"overall_status": "VALID", "findings": []}')]
        }
        result = agent.validate_claim({'claim_id': 'CG-TEST'}, fake_agent, thread_id='t-1')
        self.assertIn('VALID', result)
        called_messages = fake_agent.invoke.call_args[0][0]['messages']
        self.assertIn('CG-TEST', called_messages[0].content)


if __name__ == '__main__':
    unittest.main()
