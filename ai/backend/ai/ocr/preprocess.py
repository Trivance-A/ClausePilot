"""Scan preprocessing (OpenCV): grayscale -> deskew (Hough) and ruled-table cell detection.

Binarization is intentionally skipped: VLM/PP-OCR engines do better on the original image (05_OCR_Pipeline §3-④).
"""

import math

import cv2
import numpy as np

MAX_SKEW_DEG = 15.0
MIN_SKEW_DEG = 0.3


def estimate_skew(gray: np.ndarray) -> float:
    """Median angle (degrees, image coords: y down) of long near-horizontal Hough lines over smeared text lines.
    Estimated on a ~1200px-wide copy: the angle is scale-free and Hough is unreliable on 300dpi glyph sizes."""
    scale = 1200 / gray.shape[1]
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    bw = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)))  # merge glyphs into line blobs
    edges = cv2.Canny(bw, 50, 150)
    segs = cv2.HoughLinesP(edges, 1, np.pi / 1800, threshold=80, minLineLength=small.shape[1] // 10, maxLineGap=20)
    if segs is None:
        return 0.0
    angles = [math.degrees(math.atan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in segs.reshape(-1, 4)]
    angles = [a for a in angles if abs(a) < MAX_SKEW_DEG]
    return float(np.median(angles)) if angles else 0.0


def deskew(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    """Returns (deskewed image, inverse 2x3 affine mapping deskewed px -> original px, or None if untouched)."""
    angle = estimate_skew(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    if abs(angle) < MIN_SKEW_DEG:
        return bgr, None
    h, w = bgr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(bgr, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated, cv2.invertAffineTransform(m)


def map_box(box: tuple[float, float, float, float], inv: np.ndarray | None, w: int, h: int) -> tuple[float, float, float, float]:
    """Axis-aligned bounds of a deskewed-image box mapped back onto the original page image."""
    if inv is None:
        return box
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], dtype=np.float64) @ inv.T
    return (
        max(0.0, pts[:, 0].min()),
        max(0.0, pts[:, 1].min()),
        min(float(w), pts[:, 0].max()),
        min(float(h), pts[:, 1].max()),
    )


def _rank(values: list[int], tol: int) -> dict[int, int]:
    """Cluster coordinates within `tol` px and give each value its 1-based cluster index."""
    ranks, idx, last = {}, 0, None
    for v in sorted(set(values)):
        if last is None or v - last > tol:
            idx += 1
        ranks[v], last = idx, v
    return ranks


def detect_table_cells(gray: np.ndarray) -> tuple[np.ndarray, list[tuple[str, tuple[int, int, int, int]]]]:
    """Ruled tables only: morphological horizontal/vertical lines -> grid holes = cells.
    Returns (ruling-line mask, [("{table}/r{row},c{col}", box px)]); the mask is erased before OCR because
    engines read across cell borders otherwise."""
    h, w = gray.shape
    bw = cv2.adaptiveThreshold(~gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 30, 10), 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 60, 10))))
    lines = cv2.bitwise_or(horiz, vert)
    grid = cv2.dilate(lines, np.ones((3, 3), np.uint8))
    contours, hier = cv2.findContours(grid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return lines, []
    hier = hier.reshape(-1, 4)
    by_table: dict[int, list[tuple[int, int, int, int]]] = {}
    for i, cnt in enumerate(contours):
        parent = hier[i][3]
        if parent == -1:  # outer outline of a grid; holes inside it are the cells
            continue
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw >= 20 and ch >= 12 and cw * ch < 0.5 * w * h:
            by_table.setdefault(parent, []).append((x, y, x + cw, y + ch))
    cells: list[tuple[str, tuple[int, int, int, int]]] = []
    for t, boxes in enumerate(by_table.values()):
        if len(boxes) < 2:  # a lone framed box is not a table
            continue
        rows, cols = _rank([b[1] for b in boxes], 10), _rank([b[0] for b in boxes], 10)
        cells.extend((f"{t}/r{rows[b[1]]},c{cols[b[0]]}", b) for b in boxes)  # "t/" keeps tables apart
    return lines, cells


def cell_of(box, cells) -> str | None:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return next((key for key, (x0, y0, x1, y1) in cells if x0 <= cx <= x1 and y0 <= cy <= y1), None)
