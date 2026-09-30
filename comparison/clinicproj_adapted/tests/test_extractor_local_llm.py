import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ADAPTED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADAPTED))


class BuildLocalLlmTests(unittest.TestCase):
    def test_build_local_llm_points_at_the_local_ollama_endpoint(self):
        from extractor import build_local_llm
        llm = build_local_llm()
        self.assertEqual(llm.openai_api_base, 'http://localhost:11434/v1')
        self.assertEqual(llm.model_name, 'gemma3:4b')

    def test_extract_claim_json_uses_build_local_llm_by_default(self):
        import extractor

        class FakeResponse:
            content = '{"claim_id": "CG-TEST", "patient": {"id": null, "name": null}}'

        class FakeLlm:
            def invoke(self, prompt):
                return FakeResponse()

        with patch.object(extractor, 'build_local_llm', return_value=FakeLlm()) as built:
            result = extractor.extract_claim_json(str(ADAPTED / 'policies' / 'sample_policy.txt'))
        built.assert_called_once()
        self.assertEqual(result['claim_id'], 'CG-TEST')


if __name__ == '__main__':
    unittest.main()
