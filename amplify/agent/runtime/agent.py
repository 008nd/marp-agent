"""OpenAI-based AgentCore runtime entrypoint."""

import asyncio
import base64
import json
import os
import time
import traceback
import uuid
from datetime import datetime, timedelta

import boto3
import httpx
from bedrock_agentcore import BedrockAgentCoreApp
from openai import OpenAI

from config import get_system_prompt
from exports import (
    generate_editable_pptx,
    generate_pdf,
    generate_pptx,
    generate_standalone_html,
    generate_thumbnail,
)
from tools import (
    build_output_slide_tool_description,
    generate_tweet_url,
    get_generated_markdown,
    get_generated_tweet_url,
    get_last_search_result,
    output_slide,
    reset_generated_markdown,
    reset_generated_tweet_url,
    reset_last_search_result,
    web_search,
)

app = BedrockAgentCoreApp()

OPENAI_DEFAULT_MODEL = "gpt-5.2"
OPENAI_MODEL_MAP = {
    "standard": OPENAI_DEFAULT_MODEL,
}
OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.4"))
OPENAI_TIMEOUT_SEC = float(os.environ.get("OPENAI_TIMEOUT_SEC", "120"))
OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "1"))
MAX_TOOL_ITERATIONS = int(os.environ.get("OPENAI_MAX_TOOL_ITERATIONS", "5"))
MAX_SESSION_MESSAGES = int(os.environ.get("OPENAI_MAX_SESSION_MESSAGES", "40"))
EXPORT_KEEPALIVE_INTERVAL_SEC = 5.0

_openai_client: OpenAI | None = None
_session_messages: dict[str, list[dict]] = {}
_s3_client = None


def resolve_model(model_type: str) -> str:
    if not model_type:
        return OPENAI_DEFAULT_MODEL
    return OPENAI_MODEL_MAP.get(model_type, OPENAI_DEFAULT_MODEL)


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        base_url = os.environ.get("OPENAI_BASE_URL") or None
        if base_url and not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        if not base_url:
            base_url = "https://api.openai.com/v1"

        print(f"[INFO] OpenAI client initialized with base_url: {base_url}", flush=True)
        _openai_client = OpenAI(api_key=api_key, base_url=base_url)

    return _openai_client


def build_openai_tools(theme: str) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the web for up-to-date information. "
                    "If you use this, add a final references slide with <!-- _class: tinytext -->."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "output_slide",
                "description": build_output_slide_tool_description(theme),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "markdown": {"type": "string", "description": "Full Marp markdown"},
                    },
                    "required": ["markdown"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_tweet_url",
                "description": "Generate a tweet intent URL from the given tweet text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tweet_text": {"type": "string", "description": "Tweet content (<=100 chars)"},
                    },
                    "required": ["tweet_text"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _get_session_key(session_id: str | None, model_type: str, theme: str) -> str | None:
    if not session_id:
        return None
    return f"{session_id}:{model_type}:{theme}"


def _trim_session_messages(messages: list[dict]) -> list[dict]:
    if len(messages) <= MAX_SESSION_MESSAGES:
        return messages
    if messages and messages[0].get("role") == "system":
        return [messages[0]] + messages[-(MAX_SESSION_MESSAGES - 1) :]
    return messages[-MAX_SESSION_MESSAGES:]


def _get_session_messages(session_id: str | None, model_type: str, theme: str) -> list[dict]:
    session_key = _get_session_key(session_id, model_type, theme)
    system_prompt = get_system_prompt(theme)
    if not session_key:
        return [{"role": "system", "content": system_prompt}]
    if session_key not in _session_messages:
        _session_messages[session_key] = [{"role": "system", "content": system_prompt}]
    return _session_messages[session_key]


def _store_session_messages(session_id: str | None, model_type: str, theme: str, messages: list[dict]) -> None:
    session_key = _get_session_key(session_id, model_type, theme)
    if not session_key:
        return
    _session_messages[session_key] = _trim_session_messages(messages)


def _safe_json_loads(value: str) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_web_search_error(result: str) -> bool:
    if not result:
        return False
    lower = result.lower()
    return (
        result.startswith("web_search:")
        or "検索エラー" in result
        or "apiキー未設定" in result
        or "Web検索機能は現在利用できません" in result
        or "無料枠が枯渇" in result
        or "rate limit" in lower
        or "quota" in lower
        or "usage limit" in lower
        or "exceeds your plan" in lower
    )


def _is_retryable_openai_error(err: Exception) -> bool:
    return isinstance(
        err,
        (
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
            httpx.PoolTimeout,
        ),
    ) or "incomplete chunked read" in str(err).lower() or "peer closed connection" in str(err).lower()


def _run_tool(tool_name: str, tool_args: dict) -> str:
    if tool_name == "web_search":
        query = tool_args.get("query", "")
        if not query:
            return "web_search: query is required"
        return web_search(query)
    if tool_name == "output_slide":
        markdown = tool_args.get("markdown", "")
        if not markdown:
            return "output_slide: markdown is required"
        return output_slide(markdown)
    if tool_name == "generate_tweet_url":
        tweet_text = tool_args.get("tweet_text", "")
        if not tweet_text:
            return "generate_tweet_url: tweet_text is required"
        return generate_tweet_url(tweet_text)
    return f"Unknown tool: {tool_name}"


def extract_markdown(text: str) -> str | None:
    import re

    match = re.search(r"```markdown\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return None


def extract_marp_markdown_from_text(text: str) -> str | None:
    import re

    if not text:
        return None
    if "marp:" not in text and 'marp\\":' not in text:
        return None

    json_arg_pattern = r'<\|tool_call_argument_begin\|>\s*(\{[\s\S]*?\})\s*<\|tool_call_end\|>'
    json_match = re.search(json_arg_pattern, text)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            markdown = data.get("markdown")
            if isinstance(markdown, str) and "marp: true" in markdown:
                return markdown

    text_lower = text.lower()
    if "marp: true" not in text_lower:
        return None

    match = re.search(r"(---\s*[\r\n]+marp:\s*true[\s\S]*?)(?:<\|tool_call|$)", text, re.IGNORECASE)
    markdown = None
    if match:
        markdown = match.group(1).strip()
    else:
        match = re.search(r"(marp:\s*true[\s\S]*?)(?:<\|tool_call|$)", text, re.IGNORECASE)
        if match:
            markdown = "---\n" + match.group(1).strip()

    if not markdown:
        return None

    markdown = re.sub(r"<\|[^>]+\|>", "", markdown)
    lines = markdown.split("\n")
    while lines and (lines[-1].strip().startswith("<|") or not lines[-1].strip()):
        lines.pop()
    return "\n".join(lines) if lines else None


def extract_slide_title(markdown: str) -> str | None:
    import re

    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def inject_ogp_tags(html: str, title: str, image_url: str, page_url: str) -> str:
    import html as html_escape

    safe_title = html_escape.escape(title)
    ogp_tags = f"""
    <meta property="og:title" content="{safe_title}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{page_url}">
    <meta property="og:image" content="{image_url}">
    <meta property="og:description" content="パワポ作るマンで作成したスライド">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{safe_title}">
    <meta name="twitter:image" content="{image_url}">
    """
    return html.replace("</head>", f"{ogp_tags}</head>")


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def share_slide(markdown: str, theme: str = "gradient") -> dict:
    bucket_name = os.environ.get("SHARED_SLIDES_BUCKET")
    cloudfront_domain = os.environ.get("CLOUDFRONT_DOMAIN")
    if not bucket_name or not cloudfront_domain:
        raise RuntimeError("共有機能が設定されていません（環境変数未設定）")

    slide_id = str(uuid.uuid4())
    s3_client = get_s3_client()

    try:
        thumbnail_bytes = generate_thumbnail(markdown, theme)
        thumbnail_key = f"slides/{slide_id}/thumbnail.png"
        s3_client.put_object(
            Bucket=bucket_name,
            Key=thumbnail_key,
            Body=thumbnail_bytes,
            ContentType="image/png",
        )
        thumbnail_url = f"https://{cloudfront_domain}/{thumbnail_key}"
    except Exception as exc:
        print(f"[WARN] Thumbnail generation failed: {exc}", flush=True)
        thumbnail_url = None

    share_url = f"https://{cloudfront_domain}/slides/{slide_id}/index.html"
    html_content = generate_standalone_html(markdown, theme)
    if thumbnail_url:
        title = extract_slide_title(markdown) or "スライド"
        html_content = inject_ogp_tags(html_content, title, thumbnail_url, share_url)

    s3_client.put_object(
        Bucket=bucket_name,
        Key=f"slides/{slide_id}/index.html",
        Body=html_content.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )

    expires_at = int((datetime.utcnow() + timedelta(days=7)).timestamp())
    return {"slideId": slide_id, "url": share_url, "expiresAt": expires_at}


async def _wait_with_keepalive(task: asyncio.Future, label: str):
    while not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=EXPORT_KEEPALIVE_INTERVAL_SEC)
        except asyncio.TimeoutError:
            yield {"type": "progress", "message": f"{label}処理中..."}


async def _handle_export(current_markdown: str, theme: str, label: str, event_type: str, export_fn):
    loop = asyncio.get_event_loop()
    task = loop.run_in_executor(None, export_fn, current_markdown, theme)
    async for event in _wait_with_keepalive(task, label):
        yield event
    payload = base64.b64encode(task.result()).decode("utf-8")
    yield {"type": event_type, "data": payload}


@app.entrypoint
async def invoke(payload, context=None):
    reset_generated_markdown()
    reset_generated_tweet_url()
    reset_last_search_result()

    user_message = payload.get("prompt", "")
    action = payload.get("action", "chat")
    current_markdown = payload.get("markdown", "")
    model_type = payload.get("model_type", "standard")
    session_id = getattr(context, "session_id", None) if context else None
    theme = payload.get("theme", "gradient")

    print(
        f"[INFO] Invoke received: action={action} model_type={model_type} session_id={session_id} theme={theme}",
        flush=True,
    )

    try:
        if action == "export_pdf" and current_markdown:
            async for event in _handle_export(current_markdown, theme, "PDF", "pdf", generate_pdf):
                yield event
            return
        if action == "export_pptx" and current_markdown:
            async for event in _handle_export(current_markdown, theme, "PPTX", "pptx", generate_pptx):
                yield event
            return
        if action == "export_pptx_editable" and current_markdown:
            async for event in _handle_export(current_markdown, theme, "編集可能PPTX", "pptx", generate_editable_pptx):
                yield event
            return
        if action == "share_slide" and current_markdown:
            loop = asyncio.get_event_loop()
            task = loop.run_in_executor(None, share_slide, current_markdown, theme)
            async for event in _wait_with_keepalive(task, "共有"):
                yield event
            result = task.result()
            yield {"type": "share_result", "url": result["url"], "expiresAt": result["expiresAt"]}
            return
    except Exception as exc:
        print(f"[ERROR] Export/share failed: {exc}", flush=True)
        yield {"type": "error", "message": str(exc)}
        return

    if current_markdown:
        user_message = (
            "Current slide markdown:\n"
            f"```markdown\n{current_markdown}\n```\n\n"
            f"User request: {user_message}"
        )

    model_name = resolve_model(model_type)
    messages = _get_session_messages(session_id, model_type, theme)
    messages.append({"role": "user", "content": user_message})
    tools = build_openai_tools(theme)

    web_search_executed = False
    full_text_response = ""
    tool_iterations = 0

    yield {"type": "progress", "message": "処理中..."}

    while tool_iterations < MAX_TOOL_ITERATIONS:
        tool_iterations += 1
        tool_calls: dict[int, dict] = {}
        assistant_text = ""
        had_stream_output = False

        attempt = 0
        while True:
            try:
                print(
                    f"[INFO] OpenAI request start: model={model_name} session_id={session_id} action={action} attempt={attempt + 1}/{OPENAI_MAX_RETRIES + 1}",
                    flush=True,
                )
                stream = get_openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=OPENAI_TEMPERATURE,
                    stream=True,
                )
                for chunk in stream:
                    if not getattr(chunk, "choices", None):
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta
                    if getattr(delta, "content", None):
                        assistant_text += delta.content
                        full_text_response += delta.content
                        had_stream_output = True
                        yield {"type": "text", "data": delta.content}
                    if getattr(delta, "tool_calls", None):
                        for call in delta.tool_calls:
                            idx = call.index
                            entry = tool_calls.get(idx) or {"id": None, "name": "", "arguments": ""}
                            if getattr(call, "id", None):
                                entry["id"] = call.id
                            if getattr(call, "function", None):
                                if getattr(call.function, "name", None):
                                    entry["name"] = call.function.name
                                if getattr(call.function, "arguments", None):
                                    entry["arguments"] += call.function.arguments
                            tool_calls[idx] = entry
                            had_stream_output = True
                break
            except Exception as exc:
                retryable = _is_retryable_openai_error(exc)
                if retryable and attempt < OPENAI_MAX_RETRIES and not had_stream_output:
                    wait_sec = min(4.0, 1.0 * (2 ** attempt))
                    print(
                        f"[WARN] OpenAI stream error (retryable): model={model_name} session_id={session_id} action={action} error={type(exc).__name__}: {exc}. Retrying in {wait_sec:.1f}s",
                        flush=True,
                    )
                    time.sleep(wait_sec)
                    attempt += 1
                    continue
                print(
                    "[ERROR] OpenAI stream failed:"
                    f" model={model_name} session_id={session_id} action={action}"
                    f" base_url={'set' if os.environ.get('OPENAI_BASE_URL') else 'default'}"
                    f" error={type(exc).__name__}: {exc}",
                    flush=True,
                )
                print(traceback.format_exc(), flush=True)
                yield {"type": "error", "message": str(exc)}
                return

        if tool_calls:
            assistant_message = {"role": "assistant", "content": assistant_text or None, "tool_calls": []}
            for entry in tool_calls.values():
                call_id = entry["id"] or f"call_{uuid.uuid4().hex}"
                assistant_message["tool_calls"].append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": entry["name"],
                            "arguments": entry["arguments"] or "{}",
                        },
                    }
                )
            messages.append(assistant_message)

            for tool_call in assistant_message["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                args = _safe_json_loads(tool_call["function"]["arguments"])
                if tool_name == "web_search":
                    web_search_executed = True
                    query = args.get("query") if isinstance(args, dict) else None
                    if query:
                        yield {"type": "tool_use", "data": tool_name, "query": query}
                    else:
                        yield {"type": "tool_use", "data": tool_name}
                else:
                    yield {"type": "tool_use", "data": tool_name}

                try:
                    tool_result = _run_tool(tool_name, args if isinstance(args, dict) else {})
                except Exception as exc:
                    print(
                        "[ERROR] Tool execution failed:"
                        f" tool={tool_name} session_id={session_id} action={action}"
                        f" error={type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    print(traceback.format_exc(), flush=True)
                    yield {"type": "error", "message": str(exc)}
                    return

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_result,
                    }
                )
                if tool_name == "web_search" and _is_web_search_error(tool_result):
                    messages.append({"role": "assistant", "content": tool_result})
                    _store_session_messages(session_id, model_type, theme, messages)
                    yield {"type": "text", "data": tool_result}
                    yield {"type": "done"}
                    return
            continue

        messages.append({"role": "assistant", "content": assistant_text})
        break
    else:
        yield {"type": "error", "message": "Tool loop exceeded max iterations"}
        return

    fallback_markdown = get_generated_markdown() or extract_marp_markdown_from_text(full_text_response) or extract_markdown(full_text_response)
    markdown_to_send = get_generated_markdown() or fallback_markdown

    if web_search_executed and not markdown_to_send and get_last_search_result():
        try:
            force_messages = messages + [
                {
                    "role": "system",
                    "content": "You must call output_slide now. Do not call web_search. Output full Marp markdown.",
                }
            ]
            force_response = get_openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).chat.completions.create(
                model=model_name,
                messages=force_messages,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "output_slide"}},
                temperature=OPENAI_TEMPERATURE,
            )
            choice = force_response.choices[0] if getattr(force_response, "choices", None) else None
            force_message = choice.message if choice else None
            if force_message:
                tool_calls = getattr(force_message, "tool_calls", None) or []
                if tool_calls:
                    for call in tool_calls:
                        func = getattr(call, "function", None)
                        tool_name = getattr(func, "name", "") if func else ""
                        args = _safe_json_loads(getattr(func, "arguments", "") if func else "")
                        yield {"type": "tool_use", "data": tool_name}
                        tool_result = _run_tool(tool_name, args if isinstance(args, dict) else {})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": getattr(call, "id", f"call_{uuid.uuid4().hex}"),
                                "content": tool_result,
                            }
                        )
                elif getattr(force_message, "content", None):
                    extracted = extract_marp_markdown_from_text(force_message.content) or extract_markdown(force_message.content)
                    if extracted:
                        reset_generated_markdown()
                        output_slide(extracted)
        except Exception as exc:
            print(f"[ERROR] OpenAI forced output failed: {exc}", flush=True)
            print(traceback.format_exc(), flush=True)

        markdown_to_send = get_generated_markdown() or fallback_markdown

    if markdown_to_send:
        yield {"type": "markdown", "data": markdown_to_send}
    elif web_search_executed and get_last_search_result():
        last_search_result = get_last_search_result()
        truncated_result = last_search_result[:500]
        if len(last_search_result) > 500:
            truncated_result += "..."
        yield {
            "type": "text",
            "data": f"Web検索結果:\n\n{truncated_result}\n\n---\nスライド生成に失敗しました。もう一度お試しください。",
        }

    _store_session_messages(session_id, model_type, theme, messages)

    tweet_url = get_generated_tweet_url()
    if tweet_url:
        yield {"type": "tweet_url", "data": tweet_url}

    yield {"type": "done"}


if __name__ == "__main__":
    app.run()
