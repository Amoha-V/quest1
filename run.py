#!/usr/bin/env python3
"""Start the Frame Finder API:  python run.py"""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("service.main:app", host="127.0.0.1", port=8000, reload=True)
