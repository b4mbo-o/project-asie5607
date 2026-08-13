#!/usr/bin/env bash
# Exact-good2 U3 ch21 capture -> aligned standard MPEG-TS.
# The original USB handle remains alive after conversion; no USB reset is used.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CHANNEL="${U3_CHANNEL:-21}"
OUT=""

usage() {
  echo "usage: $0 [--channel 13..62] [--output FILE] [FILE]"
  echo "       U3_KEEPALIVE_SECONDS=N  post-capture hold (0=until Ctrl-C; default)"
}

while (($#)); do
  case "$1" in
    -c|--channel)
      [[ $# -ge 2 ]] || { usage >&2; exit 1; }
      CHANNEL="$2"
      shift 2
      ;;
    -o|--output)
      [[ $# -ge 2 ]] || { usage >&2; exit 1; }
      OUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      [[ -z "$OUT" ]] || { echo "multiple output files specified" >&2; exit 1; }
      OUT="$1"
      shift
      ;;
  esac
done

[[ "$CHANNEL" =~ ^[0-9]+$ ]] && (( CHANNEL >= 13 && CHANNEL <= 62 )) || {
  echo "terrestrial physical channel must be 13..62 (got: $CHANNEL)" >&2
  exit 1
}

OUT="${OUT:-/tmp/u3-ch${CHANNEL}-$(date +%Y%m%d-%H%M%S).ts}"
RAW="${U3_RAW_OUT:-${OUT%.ts}.ep81.raw}"
ALIGNED="${U3_ALIGNED_OUT:-${OUT%.ts}.ep81-aligned.rawts}"
READY="${U3_CAPTURE_READY:-${RAW}.capture-ready}"
BUS="${U3_BUS:-2}"
PORT="${U3_PORT:-2}"
SECONDS_BULK="${U3_BULK_SECONDS:-12}"
KEEPALIVE_SECONDS="${U3_KEEPALIVE_SECONDS:-0}"
B25_OUT="${U3_B25_OUT:-}"
B25="${U3_B25_BIN:-$ROOT/downloads/github/recfriio/arib25/b25}"
RECEIVER_PID=""

[[ "$SECONDS_BULK" =~ ^[1-9][0-9]*$ ]] || {
  echo "U3_BULK_SECONDS must be a positive integer" >&2
  exit 1
}
[[ "$KEEPALIVE_SECONDS" =~ ^[0-9]+$ ]] || {
  echo "U3_KEEPALIVE_SECONDS must be a non-negative integer" >&2
  exit 1
}
for path in "$RAW" "$ALIGNED" "$OUT"; do
  [[ ! -e "$path" ]] || { echo "refusing to overwrite: $path" >&2; exit 1; }
done

cleanup() {
  if [[ -n "$RECEIVER_PID" ]] && kill -0 "$RECEIVER_PID" 2>/dev/null; then
    kill -- "-$RECEIVER_PID" 2>/dev/null || true
    wait "$RECEIVER_PID" 2>/dev/null || true
  fi
  rm -f "$READY"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rm -f "$READY"
echo "== U3 exact-good2 terrestrial pipeline =="
echo "channel=$CHANNEL raw=$RAW output=$OUT bus=$BUS port=$PORT"

setsid env PYTHONPATH="$ROOT/scripts" python3 -u \
  "$ROOT/scripts/run_u3_full_secure_terrestrial.py" \
  --bus "$BUS" --port "$PORT" --channel "$CHANNEL" \
  --seconds "$SECONDS_BULK" --hold-after "$KEEPALIVE_SECONDS" \
  --out "$RAW" --ready-file "$READY" &
RECEIVER_PID=$!

while [[ ! -s "$READY" ]]; do
  if ! kill -0 "$RECEIVER_PID" 2>/dev/null; then
    set +e
    wait "$RECEIVER_PID"
    rc=$?
    set -e
    RECEIVER_PID=""
    echo "U3 receiver exited before capture completion (exit=$rc)" >&2
    exit 2
  fi
  sleep 0.1
done

capture_rc="$(sed -n 's/^capture_exit=//p' "$READY")"
[[ "$capture_rc" == 0 ]] || {
  echo "U3 Bulk capture failed (exit=${capture_rc:-unknown})" >&2
  exit 2
}
[[ -s "$RAW" ]] || { echo "U3 EP81 returned no payload" >&2; exit 2; }

PYTHONPATH="$ROOT/scripts" python3 \
  "$ROOT/scripts/check_u3_exact_good2_capture.py" "$RAW" \
  --aligned-out "$ALIGNED" --standard-out "$OUT" --trusted-exact-session
python3 "$ROOT/scripts/inspect_ts_ca.py" "$OUT"
if [[ -n "$B25_OUT" ]]; then
  [[ -x "$B25" ]] || {
    echo "set U3_B25_BIN to an installed ARIB STD-B25 tool" >&2
    exit 3
  }
  [[ ! -e "$B25_OUT" ]] || {
    echo "refusing to overwrite B25 output: $B25_OUT" >&2
    exit 3
  }
  "$B25" -p0 -v0 "$OUT" "$B25_OUT"
  echo "B-CAS decoded output=$B25_OUT"
fi
echo "done raw=$RAW aligned=$ALIGNED standard_ts=$OUT"

if [[ "$KEEPALIVE_SECONDS" == 0 ]]; then
  echo "U3 is being kept active on the original handle; press Ctrl-C to stop."
else
  echo "U3 will remain active for ${KEEPALIVE_SECONDS}s after capture."
fi
set +e
wait "$RECEIVER_PID"
rc=$?
set -e
RECEIVER_PID=""
exit "$rc"
