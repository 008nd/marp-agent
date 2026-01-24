import subprocess
import tempfile
import base64
import os
from pathlib import Path

from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent, tool
from tavily import TavilyClient

# Tavily クライアント初期化（APIキーがある場合のみ）
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


@tool
def web_search(query: str) -> str:
    """Web検索を実行して最新情報を取得します。スライド作成に必要な情報を調べる際に使用してください。

    Args:
        query: 検索クエリ（日本語または英語）

    Returns:
        検索結果のテキスト
    """
    if not tavily_client:
        return "Web検索機能は現在利用できません（APIキー未設定）"

    try:
        context = tavily_client.get_search_context(
            query=query,
            max_results=5,
            search_depth="advanced",
        )
        return context
    except Exception as e:
        return f"検索エラー: {str(e)}"

SYSTEM_PROMPT = """あなたは「パワポ作るマン」、プロフェッショナルなスライド作成AIアシスタントです。

## 役割
ユーザーの指示に基づいて、Marp形式のマークダウンでスライドを作成・編集します。
デザインや構成についてのアドバイスも積極的に行います。

## スライド作成ルール
- フロントマターには以下を含める：
  ```yaml
  ---
  marp: true
  theme: default
  class: invert
  size: 16:9
  paginate: true
  ---
  ```
- スライド区切りは `---` を使用
- 1枚目はタイトルスライド（タイトル + サブタイトル）
- 箇条書きは1スライドあたり3〜5項目に抑える
- 絵文字は使用しない（シンプルでビジネスライクに）
- 情報は簡潔に、キーワード中心で

## Web検索
最新の情報が必要な場合は、web_searchツールを使って調べてからスライドを作成してください。
ユーザーが「〇〇について調べて」「最新の〇〇」などと言った場合は積極的に検索を活用します。

## 出力形式
スライドを生成・編集したら、マークダウン全文を ```markdown コードブロックで出力してください。
"""

app = BedrockAgentCoreApp()

agent = Agent(
    model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    system_prompt=SYSTEM_PROMPT,
    tools=[web_search],
)


def extract_markdown(text: str) -> str | None:
    """レスポンスからマークダウンを抽出"""
    import re
    pattern = r"```markdown\s*([\s\S]*?)\s*```"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return None


def generate_pdf(markdown: str) -> bytes:
    """Marp CLIでPDFを生成"""
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / "slide.md"
        pdf_path = Path(tmpdir) / "slide.pdf"

        md_path.write_text(markdown, encoding="utf-8")

        result = subprocess.run(
            [
                "marp",
                str(md_path),
                "--pdf",
                "--allow-local-files",
                "-o", str(pdf_path),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Marp CLI error: {result.stderr}")

        return pdf_path.read_bytes()


@app.entrypoint
async def invoke(payload):
    """エージェント実行（ストリーミング対応）"""
    user_message = payload.get("prompt", "")
    action = payload.get("action", "chat")  # chat or export_pdf
    current_markdown = payload.get("markdown", "")

    if action == "export_pdf" and current_markdown:
        # PDF出力
        try:
            pdf_bytes = generate_pdf(current_markdown)
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
            yield {"type": "pdf", "data": pdf_base64}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
        return

    # チャット（スライド生成・編集）
    if current_markdown:
        user_message = f"現在のスライド:\n```markdown\n{current_markdown}\n```\n\nユーザーの指示: {user_message}"

    stream = agent.stream_async(user_message)

    full_response = ""
    async for event in stream:
        if "data" in event:
            chunk = event["data"]
            full_response += chunk
            yield {"type": "text", "data": chunk}

    # マークダウンを抽出して送信
    markdown = extract_markdown(full_response)
    if markdown:
        yield {"type": "markdown", "data": markdown}

    yield {"type": "done"}


if __name__ == "__main__":
    app.run()
