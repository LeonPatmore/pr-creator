from pathlib import Path


class PRInterface:
    @staticmethod
    def create_or_update_pr(repo_path: Path) -> None:
        raise NotImplementedError("PRInterface.create_or_update_pr is not implemented")

