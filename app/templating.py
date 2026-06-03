from pathlib import Path

from fastapi.templating import Jinja2Templates

from .config import settings

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["root_path"] = settings.root_path
