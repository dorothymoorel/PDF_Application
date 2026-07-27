import uvicorn

from transloka_api.app import create_app
from transloka_api.config import Settings

settings = Settings()
app = create_app(settings)


def run() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port)
