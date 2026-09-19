import unittest

from deepagents.middleware.skills import SkillsMiddleware

from db_agent_skills.backend import (
    SKILLS_SOURCE,
    create_agent_backend,
    create_agent_permissions,
)


class AgentBackendTests(unittest.TestCase):
    def test_loads_bundled_skills_from_virtual_mount(self) -> None:
        backend = create_agent_backend()
        middleware = SkillsMiddleware(
            backend=backend,
            sources=[SKILLS_SOURCE],
        )

        update = middleware.before_agent({}, runtime=None, config={})

        self.assertIsNotNone(update)
        assert update is not None
        skills = {
            skill["name"]: skill["path"] for skill in update["skills_metadata"]
        }
        self.assertEqual(
            skills,
            {
                "chinook": "/skills/chinook/SKILL.md",
                "northwind": "/skills/northwind/SKILL.md",
            },
        )

        reference = backend.read("/skills/northwind/references/query-guide.md")
        self.assertIsNone(reference.error)
        self.assertIn("# Northwind query guide", reference.file_data["content"])

    def test_skills_mount_rejects_path_traversal(self) -> None:
        backend = create_agent_backend()

        with self.assertRaisesRegex(ValueError, "Path traversal not allowed"):
            backend.read("/skills/../../.env")

    def test_denies_writes_to_skills_mount(self) -> None:
        permissions = create_agent_permissions()

        self.assertEqual(len(permissions), 1)
        self.assertEqual(permissions[0].operations, ["write"])
        self.assertEqual(permissions[0].paths, ["/skills", "/skills/**"])
        self.assertEqual(permissions[0].mode, "deny")


if __name__ == "__main__":
    unittest.main()
