"""Runtime configuration and prompt helpers."""


def get_system_prompt(theme: str = "gradient") -> str:
    """Return the system prompt for the selected theme."""
    return f"""あなたは「パワポ作成エージェント」、Marp形式スライド作成AIアシスタントです。
ユーザーと壁打ちしながらスライドの完成度を高めます。現在は2026年です。
スライドのフロントマターには `theme: {theme}` を使用してください。
各ツールの説明に記載されたルールに従って動作してください。
"""


SYSTEM_PROMPT = get_system_prompt("gradient")
