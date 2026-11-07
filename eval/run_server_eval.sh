#!/usr/bin/env bash
# One-shot measurement on the GPU server (EC2 A10G) — paste-able from a phone browser terminal (EC2 Instance Connect).
#   curl -fsSL https://raw.githubusercontent.com/Trivance-A/ClausePilot/feat/ai-upgrade/eval/run_server_eval.sh | bash
# Clones feat/ai-upgrade into ~/ai-upgrade, finds the running vLLM (port, API key, model), runs the LLM extraction eval
# on the public forms and prints the summary. Scan docs are included only when PaddleOCR is importable here.
set -euo pipefail
DIR="$HOME/ai-upgrade"
rm -rf "$DIR" && git clone -q --depth 1 -b feat/ai-upgrade https://github.com/Trivance-A/ClausePilot "$DIR"
cd "$DIR"
python3 -m venv .venv --system-site-packages && . .venv/bin/activate
pip -q install pymupdf opencv-python-headless numpy rapidfuzz pyyaml olefile lxml img2pdf python-docx openpyxl >/dev/null

# vLLM: API key from the container's command line (or LLM_API_KEY), port 8000 or 8002
KEY="${LLM_API_KEY:-}"
if [ -z "$KEY" ] && command -v docker >/dev/null; then
  CID=$(docker ps --format '{{.ID}} {{.Image}} {{.Names}}' | grep -i vllm | head -1 | cut -d' ' -f1 || true)
  [ -n "$CID" ] && KEY=$(docker inspect --format '{{join .Config.Cmd " "}} {{join .Args " "}} {{join .Config.Env " "}}' "$CID" \
    | grep -oE -- '(--api-key[ =]|VLLM_API_KEY=)[^ ]+' | head -1 | sed -E 's/^(--api-key[ =]|VLLM_API_KEY=)//' || true)
fi
URL=""
for p in 8000 8002; do
  if curl -fsS -m 5 -H "Authorization: Bearer $KEY" "http://localhost:$p/v1/models" >/tmp/models.json 2>/dev/null; then URL="http://localhost:$p/v1"; break; fi
done
[ -z "$URL" ] && { echo "vLLM not reachable on :8000/:8002 (is it running? API key?)"; exit 1; }
MODEL=$(python3 -c 'import json;print(json.load(open("/tmp/models.json"))["data"][0]["id"])')
echo "vLLM: $URL  model: $MODEL"

GOLD=data/gold/forms
if ! python3 -c "import paddleocr" 2>/dev/null; then
  GOLD=/tmp/gold-native && rm -rf $GOLD && mkdir -p $GOLD
  for f in data/gold/forms/*.json; do grep -q '"source_type": "native"' "$f" && cp "$f" "${f%.json}.pdf" $GOLD/; done
  echo "PaddleOCR not importable here: measuring the $(ls $GOLD/*.json | wc -l) text-PDF forms only"
fi
OUT=eval/out/server-$(date +%m%d-%H%M)
PYTHONPATH=backend:. python3 -m eval.extraction --gold "$GOLD" --extractor llm --llm-url "$URL" --llm-model "$MODEL" \
  --llm-key "$KEY" --guided-json --out "$OUT" 2>&1 | tail -3
python3 - "$OUT/metrics.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print("\n=== RESULT ===")
print("field_accuracy:", m["field_accuracy"]["overall"], " bbox_mapping:", m["bbox_mapping_rate"], " bbox_iou>=0.5:", m["bbox_iou_at_0_5"])
for k, v in m["field_accuracy"]["by_field"].items():
    print(f"  {k:22s} {v}")
for st, s in m["by_source_type"].items():
    print(st, s["field_accuracy"]["overall"], "sec/doc", s["seconds_per_doc"]["mean"])
PY
