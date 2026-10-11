import logging


def setup_logging() -> None:
    """Print the app's log lines (INFO and above) with time, level and source.

    Does nothing if logging was already configured (e.g. by pytest).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # uvicorn's access log writes the full URL, query string included (where reset tokens can
    # appear). RequestLoggingMiddleware replaces it with a safer line that also has the duration
    # and request id.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
