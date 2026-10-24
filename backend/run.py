"""Uvicorn entry point. Defaults match start.sh (backend 4010); override with PORT/HOST/RELOAD."""

import os
import sys


def main():
    port = int(os.environ.get("PORT", 4010))
    host = os.environ.get("HOST", "127.0.0.1")
    reload = os.environ.get("RELOAD", "false").lower() in ("true", "1")

    try:
        import uvicorn
    except ImportError:
        print("[ERROR] uvicorn is not installed in the active environment.", file=sys.stderr)
        print("Activate the virtualenv and run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
