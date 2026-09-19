from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.state import StateBackend
from deepagents.middleware.filesystem import FilesystemPermission

from db_agent_skills.config import PROJECT_ROOT


SKILLS_SOURCE = "/skills/"
SKILLS_DIRECTORY = PROJECT_ROOT / "skills"


def create_agent_backend() -> CompositeBackend:
    """Create in-memory storage with a restricted host-backed skills mount."""
    return CompositeBackend(
        default=StateBackend(),
        routes={
            SKILLS_SOURCE: FilesystemBackend(
                root_dir=SKILLS_DIRECTORY,
                virtual_mode=True,
            )
        },
    )


def create_agent_permissions() -> list[FilesystemPermission]:
    """Prevent model-controlled file tools from modifying bundled skills."""
    return [
        FilesystemPermission(
            operations=["write"],
            paths=["/skills", "/skills/**"],
            mode="deny",
        )
    ]
