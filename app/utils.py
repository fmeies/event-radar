from fastapi.responses import RedirectResponse

from .config import settings


def redir(path: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url=f"{settings.root_path}{path}", status_code=status_code)
