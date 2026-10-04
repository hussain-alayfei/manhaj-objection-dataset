"""ASGI entrypoint for Vercel (`[tool.vercel] entrypoint`) and `uvicorn src.asgi:app`."""
import logging
import os
from pathlib import Path

if not os.getenv('VERCEL'):
    # Local development only; hosted configuration comes from the platform environment.
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(levelname)s %(name)s %(message)s')

from .api import create_app  # noqa: E402

app = create_app()
