import pytest

from ai.extract.normalize import (
    biz_no_checksum_ok,
    korean_to_int,
    normalize_amount,
    normalize_biz_no,
    normalize_company,
    normalize_date,
    normalize_due_date,
    normalize_fields,
    normalize_period,
    parse_amounts,
    parse_dates,
)

# 한글숫자 파서 30 케이스 (05_OCR_Pipeline §6 리스크 대응)
AMOUNTS = [
    ("일금 삼억오천만원정", 350_000_000),
    ("금 삼억오천만원정(₩350,000,000)", 350_000_000),
    ("금 일억이천삼백사십오만육천칠백팔십구원정", 123_456_789),
    ("금 사천오백만원정", 45_000_000),
    ("금 십만원", 100_000),
    ("금 일십만원", 100_000),
    ("금 삼십오억원", 3_500_000_000),
    ("금 이천원", 2_000),
    ("금 오백원", 500),
    ("금 일조원", 1_000_000_000_000),
    ("금 천만원", 10_000_000),
    ("금 만원", 10_000),
    ("금 구억구천구백구십구만구천구백구십구원", 999_999_999),
    ("금 삼억 오천만 원정", 350_000_000),
    ("3억 5천만원", 350_000_000),
    ("1,500만원", 15_000_000),
    ("1억2천만원", 120_000_000),
    ("금 2억원", 200_000_000),
    ("₩350,000,000", 350_000_000),
    ("￦35,000,000", 35_000_000),
    ("35,000,000원", 35_000_000),
    ("KRW 350,000,000", 350_000_000),
    ("금350,000,000원", 350_000_000),
    ("금 350,000,000원(부가세 포함)", 350_000_000),
    ("W350,000,000", 350_000_000),  # OCR reads ₩ as W
    ("금 삼억원정 (₩300,000,000)", 300_000_000),
    ("일금 칠백만원정", 7_000_000),
    ("금 육십칠만팔천원", 678_000),
    ("금 일천이백만원", 12_000_000),
    ("금 오억원(₩500,000,000) 부가가치세 별도", 500_000_000),
]


@pytest.mark.parametrize(("text", "expected"), AMOUNTS)
def test_amounts(text, expected):
    assert normalize_amount(text) == {"amount": expected}


def test_digits_win_but_both_are_reported():
    assert parse_amounts("금 삼억원정 (₩350,000,000)") == (350_000_000, 300_000_000)
    assert normalize_amount("금 삼억원정 (₩350,000,000)") == {"amount": 350_000_000}


def test_no_amount():
    assert normalize_amount("계약금액은 별도 협의") is None
    assert korean_to_int("") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026.3.5", "2026-03-05"),
        ("2026년 3월 5일", "2026-03-05"),
        ("26.03.05", "2026-03-05"),
        ("2026. 3. 5.", "2026-03-05"),
        ("2026-03-05", "2026-03-05"),
        ("2026/3/5", "2026-03-05"),
        ("March 5, 2026", "2026-03-05"),
    ],
)
def test_dates(text, expected):
    assert normalize_date(text) == {"date": expected}


def test_invalid_date_is_null():
    assert normalize_date("2026.2.30") is None
    assert normalize_date("20OO년 O월 O일") is None


def test_due_date_takes_period_end():
    assert normalize_due_date("2026.03.05 ~ 2026.12.31") == {"date": "2026-12-31"}
    assert parse_dates("착공 2026.03.05 ~ 준공 2026.12.31") == ["2026-03-05", "2026-12-31"]


def test_periods():
    assert normalize_period("2026-03-05 ~ 2027-03-04", None, None) == {"start": "2026-03-05", "end": "2027-03-04"}
    assert normalize_period("계약일로부터 준공일까지", "2026-03-05", "2026-12-31") == {"start": "2026-03-05", "end": "2026-12-31", "derived": True}
    assert normalize_period("2026년 3월 5일부터 1년간", None, None) == {"start": "2026-03-05", "end": "2027-03-04", "derived": True}
    assert normalize_period("계약일로부터 12개월", "2026-03-05", None) == {"start": "2026-03-05", "end": "2027-03-04", "derived": True}
    assert normalize_period("계약일로부터 준공일까지", None, None) is None  # nothing to resolve against


def test_biz_no():
    assert normalize_biz_no("사업자등록번호 : 214-86-11115") == {"text": "214-86-11115", "checksum_valid": True}
    assert normalize_biz_no("2148611113") == {"text": "214-86-11113", "checksum_valid": False}
    assert biz_no_checksum_ok("1234567891")
    assert normalize_biz_no("전화 02-123-4567") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("주식회사 한빛건설", "(주)한빛건설"),
        ("한빛건설 주식회사", "한빛건설(주)"),
        ("㈜한빛", "(주)한빛"),
        ("( 주 ) 한빛", "(주)한빛"),
        ('"한빛공사" 귀하', "한빛공사"),
    ],
)
def test_company(text, expected):
    assert normalize_company(text) == {"text": expected}


def test_normalize_fields_resolves_relative_period():
    out = normalize_fields({"contract_date": "2026년 3월 5일", "performance_due_date": "2026. 12. 31.", "guarantee_period": "계약일로부터 준공일까지"})
    assert out["guarantee_period"] == {"start": "2026-03-05", "end": "2026-12-31", "derived": True}
    assert out["contract_amount"] is None


def test_period_relative_start_with_explicit_end():
    assert normalize_period("계약일로부터 2027. 3. 4.까지", "2026-03-05", None) == {"start": "2026-03-05", "end": "2027-03-04", "derived": True}
