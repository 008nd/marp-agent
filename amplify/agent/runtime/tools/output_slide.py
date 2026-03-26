"""Slide output helper with overflow checks."""

import math
import re
import unicodedata

_generated_markdown: str | None = None
_overflow_retry_count: int = 0

MAX_OVERFLOW_RETRIES = 2
MAX_LINES_PER_SLIDE = 9
MAX_DISPLAY_WIDTH_PER_LINE = 48
MAX_TABLE_ROW_WIDTH = 64


def _get_display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in ("F", "W", "A"):
            width += 2
        else:
            width += 1
    return width


def _strip_markdown_formatting(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"^[-*+]\s+", "", text)
    text = re.sub(r"^\d+\.\s+", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text)
    text = re.sub(r"^>\s*", "", text)
    return text


def _estimate_visual_lines(text: str) -> int:
    stripped = text.strip()
    if stripped.startswith("|") and stripped.endswith("|"):
        return 1

    display_text = _strip_markdown_formatting(stripped)
    width = _get_display_width(display_text)
    if width <= MAX_DISPLAY_WIDTH_PER_LINE:
        return 1
    return math.ceil(width / MAX_DISPLAY_WIDTH_PER_LINE)


def _parse_slides(markdown: str) -> list[str]:
    content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", markdown, count=1, flags=re.DOTALL)
    slides = re.split(r"\n---\s*\n", content)
    return [slide.strip() for slide in slides if slide.strip()]


def _count_content_lines(slide_content: str) -> int:
    count = 0
    in_code_block = False

    for line in slide_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not stripped:
            continue
        if re.match(r"^<!--.*-->$", stripped):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue
        count += _estimate_visual_lines(stripped)

    return count


def _check_table_width(slide_content: str) -> int:
    max_width = 0
    for line in slide_content.split("\n"):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue
        width = _get_display_width(stripped)
        if width > MAX_TABLE_ROW_WIDTH:
            max_width = max(max_width, width)
    return max_width


def _check_slide_overflow(markdown: str) -> list[dict]:
    slides = _parse_slides(markdown)
    violations = []

    for index, slide in enumerate(slides, start=1):
        if re.search(r"_class:\s*(top|lead|end|tinytext)", slide):
            continue

        line_count = _count_content_lines(slide)
        if line_count > MAX_LINES_PER_SLIDE:
            violations.append(
                {
                    "slide_number": index,
                    "type": "line_overflow",
                    "line_count": line_count,
                    "excess": line_count - MAX_LINES_PER_SLIDE,
                }
            )

        table_max_width = _check_table_width(slide)
        if table_max_width > 0:
            violations.append(
                {
                    "slide_number": index,
                    "type": "table_overflow",
                    "max_width": table_max_width,
                    "excess": table_max_width - MAX_TABLE_ROW_WIDTH,
                }
            )

    return violations


def get_generated_markdown() -> str | None:
    return _generated_markdown


def reset_generated_markdown() -> None:
    global _generated_markdown, _overflow_retry_count
    _generated_markdown = None
    _overflow_retry_count = 0


def build_output_slide_tool_description(theme: str = "gradient") -> str:
    return f"""生成したスライドのマークダウンを出力します。スライドを作成・編集したら必ずこのツールを使って出力してください（テキストで直接書き出さない）。

## Marpフォーマットルール
- フロントマター: `marp: true`, `theme: {theme}`, `size: 16:9`, `paginate: true`
- スライド区切り: `---`
- 1枚目はタイトルスライド（`<!-- _class: top --><!-- _paginate: skip -->`付き）
- 1スライドの行数は7〜8行を目標、9行が上限
- 1行が長いと折り返しで実質2行になるため、全角24文字（半角48文字）程度に抑える
- 絵文字は禁止
- ==ハイライト==記法は禁止

## 構成テクニック
- 3〜4枚ごとに `<!-- _class: lead -->` の中タイトルスライドを挿入
- 同じ表現パターンが2枚連続しないよう、箇条書き・本文+箇条書き・小見出し・表・まとめを混ぜる
- Web検索時は最後に `<!-- _class: tinytext -->` 付き参考文献スライドを追加
- 最後のスライドは `<!-- _class: end --><!-- _paginate: skip -->` を付けて「Thank you!」のみ表示

## 出力後のふるまい
- 出力完了後は原則しゃべらない
- バリデーションエラー時は、超過スライドを直してから再度このツールを呼ぶ
"""


def output_slide(markdown: str) -> str:
    global _generated_markdown, _overflow_retry_count

    violations = _check_slide_overflow(markdown)
    if violations and _overflow_retry_count < MAX_OVERFLOW_RETRIES:
        _overflow_retry_count += 1
        details = []
        for violation in violations:
            if violation["type"] == "line_overflow":
                details.append(
                    f"  - スライド{violation['slide_number']}: 実質{violation['line_count']}行（{violation['excess']}行超過）"
                )
            else:
                details.append(
                    f"  - スライド{violation['slide_number']}: 表の横幅超過（{violation['max_width']}文字、上限{MAX_TABLE_ROW_WIDTH}文字）"
                )
        return (
            "ページあふれ検出！以下のスライドに問題があります：\n"
            + "\n".join(details)
            + "\n修正してから再度 output_slide を呼んでください。"
            + "（行数超過→内容を減らすか分割。表の横幅超過→列数を減らすかセル内容を短くする）"
        )

    if violations:
        print(f"[WARN] Slide overflow accepted after max retries: {violations}")

    _generated_markdown = markdown
    _overflow_retry_count = 0
    return "スライドを出力しました。"
