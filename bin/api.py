import uvicorn

from settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
