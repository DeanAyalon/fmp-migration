class PipelineError(Exception):
    """Raised when a migration pipeline step fails."""
    def __init__(self, step: str, detail: str) -> None:
        self.step = step
        self.detail = detail
        super().__init__(f"{step}: {detail}")
