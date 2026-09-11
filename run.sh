#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import aiohttp, aiortc, numpy, ScreenCaptureKit, Quartz, CoreAudio, qrcode' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec /usr/bin/caffeinate -i .venv/bin/python server.py "$@"
