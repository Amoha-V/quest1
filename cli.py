#!/usr/bin/env python3
"""
MVP entrypoint for the assignment -- runs the core pipeline standalone,
no service/frontend dependencies required.

Usage:
    python cli.py --url "https://ok.ru/video/248244667877" \\
                   --text "My mind rebels at stagnation"

    python cli.py --url "..." --text "..." --force   # bypass result cache
"""
from __future__ import annotations

import argparse
import json
import sys

from core.pipeline import process_video


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Video URL")
    parser.add_argument("--text", required=True, help="Target dialogue text to locate")
    parser.add_argument("--force", action="store_true", help="Ignore cached result, reprocess")
    args = parser.parse_args()

    result = process_video(args.url, args.text, force=args.force)

    print(json.dumps(result, indent=2))

    if not result["matched"]:
        print("\nNo confident match found.", file=sys.stderr)
        return 1

    print(f"\nTimestamp : {result['timestamp']}")
    print(f"Frame     : {result['frame_number']}")
    print(f"Text      : \"{result['recognized_text']}\"")
    print(f"Image     : {result['frame_image_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
