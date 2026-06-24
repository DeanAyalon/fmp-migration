from src.config import Settings


def fms_exec_args() -> list[str]:
    # TODO: replace with real FileMaker migration commands
    return ["ls", "-la", "/tmp/migration"]


def run_migration(settings: Settings) -> None:
    raise NotImplementedError("Migration pipeline not yet implemented")
