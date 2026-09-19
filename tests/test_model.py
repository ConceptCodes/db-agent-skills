import unittest

from langchain_openrouter import ChatOpenRouter
from pydantic import SecretStr

from db_agent_skills.config import Settings
from db_agent_skills.model import create_chat_model


class ModelTests(unittest.TestCase):
    def test_resolves_openrouter_provider_prefix(self) -> None:
        settings = Settings(
            model="openrouter:openai/gpt-5.6-luna",
            openrouter_api_key=SecretStr("test-key"),
        )

        model = create_chat_model(settings)

        self.assertIsInstance(model, ChatOpenRouter)
        self.assertEqual(model.model, "openai/gpt-5.6-luna")

    def test_requires_openrouter_api_key(self) -> None:
        settings = Settings(
            model="openrouter:openai/gpt-5.6-luna",
            openrouter_api_key=None,
        )

        with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
            create_chat_model(settings)


if __name__ == "__main__":
    unittest.main()
