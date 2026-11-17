"""📘 1단계 파싱: PDF를 Unstructured '요소(Element)' 목록으로 바꿉니다.

요소 = Title, NarrativeText, ListItem, Table, Header, Footer … 처럼 '종류(category)'가 붙은 글 조각.
파싱 방법(strategy)
- fast     : PDF 안의 글자 층을 그대로 읽음. 빠르지만 표 구조와 스캔본은 못 읽음
- hi_res   : 레이아웃 모델로 페이지를 봄. 표 구조(text_as_html)를 얻을 수 있음. 느리고 첫 실행 때 모델을 내려받음
- ocr_only : 이미지에서 글자를 인식 (스캔본용, Tesseract 필요)
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings


MIN_REPEAT_LEN = 10  # 이보다 짧은 반복 글(표 열 이름 등)은 머리말·꼬리말로 보지 않음


def iter_pdfs(root: str | Path | None = None):
    for p in sorted(Path(root or settings.kb_pdf_dir).glob("*.pdf")):
        yield p


def parse_pdf(path: str | Path, strategy: str | None = None) -> list:
    """PDF 하나를 요소 목록으로."""
    from unstructured.partition.auto import partition

    strategy = strategy or settings.parse_strategy
    return partition(
        filename=str(path),
        strategy=strategy,
        languages=["kor", "eng"],
        infer_table_structure=True,
    )


def drop_header_footer(elements: list) -> list:
    """페이지마다 반복되는 머리말·꼬리말("대외비" 등)을 걸러냅니다. 03번 PDF로 확인하세요."""
    # category만 보고 지우면 안 됩니다. (fast 파싱 관찰)
    # - 03번: 본문 소제목("3. 확산 범위 조사")이 Header로 잘못 분류됨 → 지우면 본문 손실
    # - 09번: 표의 열 이름("심각도", "시간대")이 Header로 분류되고 쪽마다 반복됨 → 지우면 열 이름 손실
    # 그래서 'Header/Footer로 분류됐고, 여러 쪽에 반복되고, 문장 길이(MIN_REPEAT_LEN자 이상)인 것'만 뺍니다.
    def norm(e) -> str:
        return " ".join(e.text.split())

    pages_of: dict[str, set] = {}
    for e in elements:
        pages_of.setdefault(norm(e), set()).add(e.metadata.page_number)

    def is_boilerplate(e) -> bool:
        t = norm(e)
        return (e.category in ("Header", "Footer")
                and len(t) >= MIN_REPEAT_LEN
                and len(pages_of[t]) >= 2)

    return [e for e in elements if not is_boilerplate(e)]
