#!/usr/bin/env bash
# One-shot HDUC x64-mode6 pipeline using bundled normalized protocol data.
# No USB reset is used.  The receive URBs are queued before request 0x06.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CTL="$ROOT/tools/hduc_ctl/hduc_ctl"
FW="${HDUC_FIRMWARE:-$ROOT/firmware/as11loader_decrypted_full.bin}"
MANIFEST="${HDUC_INIT_MANIFEST:-$ROOT/data/hduc-x64-init.json}"
MATERIAL="${HDUC_MODE6_MATERIAL:-$ROOT/data/hduc-x64-mode6-material.json}"
CHANNEL="${HDUC_CHANNEL:-21}"
OUT=""

usage() {
  echo "usage: $0 [--channel 13..62] [--output FILE] [FILE]"
  echo "       HDUC_CHANNEL=N $0 [FILE]"
  echo "       HDUC_KEEPALIVE_SECONDS=N  post-capture hold (0=until Ctrl-C; default)"
  echo "       HDUC_KEEPALIVE=0          close the USB handle after capture"
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
OUT="${OUT:-/tmp/hduc-x64-ch${CHANNEL}-$(date +%Y%m%d-%H%M%S).ts}"
RAW="${HDUC_RAW_OUT:-${OUT%.ts}.raw.ts}"
BUS="${HDUC_BUS:-2}"
PORT="${HDUC_PORT:-5}"
SECONDS_BULK="${HDUC_BULK_SECONDS:-12}"
B25_OUT="${HDUC_B25_OUT:-}"
B25="${HDUC_B25_BIN:-}"
KEEPALIVE="${HDUC_KEEPALIVE:-1}"
KEEPALIVE_SECONDS="${HDUC_KEEPALIVE_SECONDS:-0}"
CAPTURE_READY="${HDUC_CAPTURE_READY:-${RAW}.capture-ready}"
RECEIVER_PID=""
CAPTURE_MARKER_OWNED=0

[[ "$SECONDS_BULK" =~ ^[1-9][0-9]*$ ]] || {
  echo "HDUC_BULK_SECONDS must be a positive integer (got: $SECONDS_BULK)" >&2
  exit 1
}
[[ "$KEEPALIVE_SECONDS" =~ ^[0-9]+$ ]] || {
  echo "HDUC_KEEPALIVE_SECONDS must be a non-negative integer (got: $KEEPALIVE_SECONDS)" >&2
  exit 1
}

have_vid_pid() {
  lsusb -d "$1" >/dev/null 2>&1
}

wait_for() {
  local id="$1" n="${2:-60}"
  for _ in $(seq 1 "$n"); do
    if have_vid_pid "$id"; then return 0; fi
    sleep 0.5
  done
  return 1
}

cleanup_receiver() {
  if [[ -n "$RECEIVER_PID" ]] && kill -0 "$RECEIVER_PID" 2>/dev/null; then
    kill "$RECEIVER_PID" 2>/dev/null || true
    wait "$RECEIVER_PID" 2>/dev/null || true
  fi
  if [[ "$CAPTURE_MARKER_OWNED" == 1 ]]; then
    rm -f "$CAPTURE_READY"
  fi
}

wait_for_capture() {
  while [[ ! -s "$CAPTURE_READY" ]]; do
    if ! kill -0 "$RECEIVER_PID" 2>/dev/null; then
      set +e
      wait "$RECEIVER_PID"
      local rc=$?
      set -e
      RECEIVER_PID=""
      echo "async receiver exited before its capture-ready marker (exit=$rc)" >&2
      return 1
    fi
    sleep 0.1
  done
  local capture_rc
  capture_rc="$(sed -n 's/^capture_exit=//p' "$CAPTURE_READY")"
  cat "$CAPTURE_READY"
  if [[ ! "$capture_rc" =~ ^[0-9]+$ ]] || (( capture_rc != 0 )); then
    set +e
    wait "$RECEIVER_PID"
    set -e
    RECEIVER_PID=""
    echo "async capture failed (exit=${capture_rc:-unknown})" >&2
    return 1
  fi
}

wait_for_keeper() {
  [[ -n "$RECEIVER_PID" ]] || return 0
  if [[ "$KEEPALIVE_SECONDS" == 0 ]]; then
    echo "HDUC runtime is being kept active on the capture handle; press Ctrl-C to stop it."
  else
    echo "HDUC runtime will remain active for ${KEEPALIVE_SECONDS}s after capture."
  fi
  set +e
  wait "$RECEIVER_PID"
  local rc=$?
  set -e
  RECEIVER_PID=""
  return "$rc"
}

trap cleanup_receiver EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ -f "$MANIFEST" ]] || { echo "missing init manifest: $MANIFEST"; exit 3; }
[[ -f "$MATERIAL" ]] || { echo "missing mode-6 material: $MATERIAL"; exit 3; }

echo "== HDUC x64 mode6 live once =="
echo "terrestrial_channel=$CHANNEL raw=$RAW output=$OUT bus=$BUS port=$PORT"

if have_vid_pid 1738:5211; then
  [[ -f "$FW" ]] || { echo "missing plaintext firmware: $FW"; exit 3; }
  "$CTL" loader-upload "$FW" --bus "$BUS" --port "$PORT"
  wait_for 3275:7080 || { echo "runtime did not appear"; exit 2; }
elif ! have_vid_pid 3275:7080; then
  echo "no HDUC on USB (1738:5211 / 3275:7080 missing)"
  exit 2
fi

# Replay the normalized initialization manifest including its settling delays.
# Nonce-bound requests are encoded against the current live session.
set +e
python3 "$ROOT/scripts/replay_hduc_manifest.py" \
  --manifest "$MANIFEST" \
  --terrestrial-channel "$CHANNEL"
REPLAY_RC=$?
set -e
echo "replay_exit=$REPLAY_RC"
(( REPLAY_RC == 0 )) || { echo "initialization replay failed" >&2; exit 2; }
have_vid_pid 3275:7080 || { echo "runtime disconnected during replay"; exit 2; }

if [[ "$KEEPALIVE" != 0 ]]; then
  # The receiver itself retains its original USB handle after capture.  A
  # detached replacement process is not reliable here: closing the original
  # owner leaves a watchdog-sized gap and job cleanup can kill the replacement.
  rm -f "$CAPTURE_READY"
  CAPTURE_MARKER_OWNED=1
  "$CTL" async-bulk --vid 0x3275 --pid 0x7080 --ep 0x81 \
    --seconds "$SECONDS_BULK" --buffers 8 --size 8192 \
    --start 0x06 --hduc-post-start --out "$RAW" \
    --hold-after "$KEEPALIVE_SECONDS" --ready-file "$CAPTURE_READY" &
  RECEIVER_PID=$!
  wait_for_capture || exit 2
else
  "$CTL" async-bulk --vid 0x3275 --pid 0x7080 --ep 0x81 \
    --seconds "$SECONDS_BULK" --buffers 8 --size 8192 \
    --start 0x06 --hduc-post-start --out "$RAW"
fi

if [[ ! -s "$RAW" ]]; then
  echo "EP81 returned no payload"
  wait_for_keeper || true
  exit 2
fi

python3 "$ROOT/scripts/transform_hduc_x64_stream.py" "$RAW" "$OUT" \
  --material "$MATERIAL" --truncate-partial
python3 "$ROOT/scripts/inspect_ts_ca.py" "$OUT"
if [[ -n "$B25_OUT" ]]; then
  [[ -n "$B25" && -x "$B25" ]] || {
    echo "set HDUC_B25_BIN to your separately installed ARIB STD-B25 tool" >&2
    exit 3
  }
  [[ ! -e "$B25_OUT" ]] || { echo "refusing to overwrite B25 output: $B25_OUT"; exit 3; }
  "$B25" -p0 -v0 "$OUT" "$B25_OUT"
  echo "B-CAS decoded output=$B25_OUT"
fi
echo "done raw=$RAW output=$OUT"
wait_for_keeper
