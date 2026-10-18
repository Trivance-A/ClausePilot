"""하이라이트 색상의 단일 소스. ExtractionResponse.color_map으로 그대로 노출되고,
PDF 내보내기(export/pdf) 오버레이 색상도 여기서 가져온다 (프론트는 색상을 하드코딩하지 않는다)."""

FIELD_COLOR_MAP: dict[str, str] = {
    "contract_name": "#FFD54F",
    "contract_amount": "#4FC3F7",
    "guarantee_amount": "#81C784",
    "contract_date": "#FF8A65",
    "performance_due_date": "#BA68C8",
    "guarantee_period": "#A1887F",
    "creditor_name": "#F06292",
    "creditor_biz_no": "#90A4AE",
}

RISK_SEVERITY_COLOR: dict[str, str] = {
    "HIGH": "#E53935",
    "MEDIUM": "#FB8C00",
    "LOW": "#FDD835",
}


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
