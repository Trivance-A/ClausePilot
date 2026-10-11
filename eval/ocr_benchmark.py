"""OCR engine benchmark on the scan docs of a gold set (05_OCR_Pipeline §5): CER / WER / line-bbox agreement.

    PYTHONPATH=backend python -m eval.ocr_benchmark --gold data/gold/synthetic --engines tesseract,paddle

Needs gold docs with source_type "scan" and the optional `text_lines` key ([{page, text, bbox}], every printed
line in reading order). Each engine runs the full scan path of ai.ocr.run_ocr (render, deskew, table ruling
removal, fragment merge), so this measures what the extractor actually receives.
- CER: char edit distance / reference chars, whitespace removed (spacing errors are what WER measures)
- WER: whitespace-token edit distance / reference tokens
- line_bbox_agreement: share of gold lines with an OCR line of IoU >= 0.5 on the same page
- cross_engine_line_agreement: share of engine A lines with an IoU >= 0.5 line from engine B
Uses no rapidfuzz, so it runs in the separate PaddleOCR venv too.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from ai.ocr import run_ocr

from eval.gold import load_gold
from eval.metrics import IOU_THRESHOLD, char_errors, iou, word_errors


def page_text(lines: list[dict], page: int, key: str = "page_no") -> str:
    return "\n".join(ln["text"] for ln in lines if ln[key] == page)


def matched(src: list[dict], src_key: str, dst: list[dict], dst_key: str) -> int:
    """How many `src` lines have a `dst` line on the same page with IoU >= 0.5."""
    return sum(any(d[dst_key] == s[src_key] and iou(s["bbox"], d["bbox"]) >= IOU_THRESHOLD for d in dst) for s in src)


def benchmark(gold_dir: Path, engines: list[str], limit: int | None = None) -> dict:
    docs = [(g, p) for g, p in load_gold(gold_dir) if g["source_type"] == "scan" and g.get("text_lines")][:limit]
    if not docs:
        raise SystemExit(f"no scan docs with text_lines in {gold_dir}")
    outputs: dict[str, dict[str, list[dict]]] = {e: {} for e in engines}
    result: dict = {"engines": {}, "n_docs": len(docs), "n_pages": len({(g["doc_id"], ln["page"]) for g, _ in docs for ln in g["text_lines"]})}
    for engine in engines:
        ce = cn = we = wn = hit = n_gold = 0
        seconds = []
        for gold, path in docs:
            t0 = time.perf_counter()
            lines = run_ocr(str(path), engine)
            seconds.append(time.perf_counter() - t0)
            outputs[engine][gold["doc_id"]] = lines
            ref = gold["text_lines"]
            for page in sorted({ln["page"] for ln in ref}):
                c = char_errors(page_text(ref, page, "page"), page_text(lines, page))
                w = word_errors(page_text(ref, page, "page"), page_text(lines, page))
                ce, cn, we, wn = ce + c[0], cn + c[1], we + w[0], wn + w[1]
            hit += matched(ref, "page", lines, "page_no")
            n_gold += len(ref)
            print(f"{engine} {gold['doc_id']}: {seconds[-1]:.1f}s", file=sys.stderr)
        result["engines"][engine] = {
            "cer": round(ce / cn, 4),
            "wer": round(we / wn, 4),
            "line_bbox_agreement": round(hit / n_gold, 4),
            "seconds_per_doc": round(sum(seconds) / len(seconds), 2),
        }
    result["cross_engine_line_agreement"] = {
        f"{a}->{b}": round(
            sum(matched(outputs[a][d], "page_no", outputs[b][d], "page_no") for d in outputs[a]) / max(1, sum(len(v) for v in outputs[a].values())), 4
        )
        for a in engines
        for b in engines
        if a != b
    }
    return result


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", required=True, type=Path)
    ap.add_argument("--engines", default="tesseract,paddle", help="comma separated: tesseract | paddle | paddle_vl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None, help="default: eval/out/<gold dir name>-ocr.json")
    args = ap.parse_args(argv)
    result = benchmark(args.gold, [e.strip() for e in args.engines.split(",") if e.strip()], args.limit)
    result["meta"] = {"gold": str(args.gold), "run_at": datetime.now().isoformat(timespec="seconds")}
    out = args.out or Path("eval/out") / f"{args.gold.name}-ocr.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
