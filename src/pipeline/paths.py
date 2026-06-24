from src.config import Settings


def clone_filename(solution: str) -> str: return f"{solution}_clone.fmp12"
def fms_databases_dir() -> str: return "/opt/FileMaker/FileMaker Server/Data/Databases"
def live_db_path(solution: str) -> str: return f"{fms_databases_dir()}/{solution}.fmp12"
def db_filename(settings: Settings) -> str: return f"{settings.solution}.fmp12"

def migration_paths(solution: str) -> dict[str, str]:
    migration_dir = "/tmp/migration"
    return {
        "dir": migration_dir,
        "clone": f"{migration_dir}/clone.fmp12",
        "source": f"{migration_dir}/source.fmp12",
        "output": f"{migration_dir}/{solution}.fmp12",
    }

