#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CTL="$ROOT/tools/hduc_ctl/hduc_ctl"

"$ROOT/scripts/extract_as11loader_firmware.py" --help >/dev/null

out13="$($CTL tune --channel 13 --dry-run)"
out62="$($CTL tune --channel 62 --dry-run)"

grep -q 'center=473143 kHz tuner_word=0x7649' <<<"$out13"
grep -q 'value=0x4903' <<<"$out13"
grep -q 'value=0x7603' <<<"$out13"
grep -q 'req=0x04 value=0x0000 index=0x0000 len=66' <<<"$out13"
grep -q 'req=0x05 value=0x1f41 index=0x00ff len=3' <<<"$out13"
grep -q 'center=767143 kHz tuner_word=0xbfc9' <<<"$out62"
grep -q 'value=0xc903' <<<"$out62"
grep -q 'value=0xbf03' <<<"$out62"

bash -n "$ROOT/scripts/run_hduc_x64_live_once.sh"
"$ROOT/scripts/hducd" --dry-run | grep -q 'socket=/tmp/hduc.sock'
"$ROOT/scripts/recpt1-hduc" --dry-run 21 1:02:03 /tmp/test.ts | \
  grep -q 'seconds=3723'
python3 "$ROOT/scripts/replay_hduc_manifest.py" \
  --manifest "$ROOT/data/hduc-x64-init.json" \
  --terrestrial-channel 21 --dry-run | grep -q 'commands=3085'

PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_control_template.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_card_template.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_good2_session_vectors.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_terrestrial_tuning.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_p10_transform.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_streaming_backend.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_channel_gate.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_persistent_retune.py" >/dev/null
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/verify_u3_satellite_tuning.py" >/dev/null
bash -n "$ROOT/scripts/run_u3_terrestrial_once.sh"
"$ROOT/scripts/u3d" --dry-run --bus 2 --port 2 --channel 21 | grep -q 'channel=21'
"$ROOT/scripts/recpt1-u3" --dry-run 21 1:02:03 /tmp/u3-test.ts | grep -q 'seconds=3723'
"$ROOT/scripts/recpt1-u3" --dry-run BS141 30 /tmp/u3-bs.ts | grep -q 'channel=BS13_0'
"$ROOT/scripts/recpt1-u3" --dry-run QVC 30 /tmp/u3-cs.ts | grep -q 'channel=CS22'
echo "smoke tests passed"
