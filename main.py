"""Vercel FastAPI entrypoint.

Vercel auto-detects FastAPI apps at root files like `main.py` and expects
an exported variable named `app`.
"""

from execution.api_server import app

