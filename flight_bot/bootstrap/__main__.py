"""Позволяет запускать: python -m bootstrap.load_references"""

import asyncio

from bootstrap.load_references import load

asyncio.run(load())
