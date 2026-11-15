#!/usr/bin/env bash
# Records the guided demo and produces demo.mp4 (captions burned in + soft English subtitle track) and demo.srt.
# Requirements: ffmpeg, node + the `playwright` npm package (Chromium), and this repo installed (pip install -e .).
# Usage: scripts/make_demo_video.sh [out_dir] ["Presenter Name"]
set -euo pipefail
OUT="${1:-demo_out}"
PRESENTER="${2:-}"
PORT=8765
mkdir -p "$OUT"

famcheck serve --port "$PORT" >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null && break; sleep 0.5; done

DEMO_URL="http://127.0.0.1:$PORT" node "$(dirname "$0")/record_demo.js" "$OUT" "$PRESENTER"

ffmpeg -y -loglevel error -i "$OUT/demo.webm" -i "$OUT/demo.srt" \
  -map 0:v -map 1:s -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -r 30 \
  -c:s mov_text -metadata:s:s:0 language=eng -movflags +faststart "$OUT/demo.mp4"
echo "done: $OUT/demo.mp4  +  $OUT/demo.srt"
