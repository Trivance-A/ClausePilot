import pytest

from eval.metrics import best_iou, char_errors, edit_distance, iou, union_box, word_errors


def test_iou():
    assert iou([0, 0, 1, 1], [0, 0, 1, 1]) == 1
    assert iou([0, 0, 1, 1], [2, 2, 3, 3]) == 0
    assert iou([0, 0, 2, 1], [1, 0, 3, 1]) == pytest.approx(1 / 3)
    assert iou([0, 0, 0, 0], [0, 0, 0, 0]) == 0  # degenerate box, no ZeroDivisionError


def test_best_iou_union_for_wrapped_value_and_page_filter():
    gold = [0.1, 0.1, 0.5, 0.2]  # value drawn over two lines -> gold is the union
    halves = [{"page_no": 1, "bbox": [0.1, 0.1, 0.5, 0.15]}, {"page_no": 1, "bbox": [0.1, 0.15, 0.3, 0.2]}]
    assert union_box([h["bbox"] for h in halves]) == [0.1, 0.1, 0.5, 0.2]
    assert best_iou(halves, 1, gold) == pytest.approx(1.0)
    assert best_iou(halves, 2, gold) == 0.0
    # exact search may return a second, far-away hit (e.g. the date repeated at the signature): the best box wins
    hits = [{"page_no": 1, "bbox": gold}, {"page_no": 1, "bbox": [0.5, 0.8, 0.9, 0.9]}]
    assert best_iou(hits, 1, gold) == 1.0


def test_edit_distance_chars_and_tokens():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == 3
    assert edit_distance(["계약", "금액"], ["계약", "금엑", "원"]) == 2


def test_cer_ignores_spacing_wer_does_not():
    assert char_errors("계약 금액 : 금 3억원", "계약금액:금3억원") == (0, 9)
    assert char_errors("계약금액", "계악금액") == (1, 4)
    assert word_errors("계약 금액 : 금 3억원", "계약금액 : 금 3억원") == (2, 5)
