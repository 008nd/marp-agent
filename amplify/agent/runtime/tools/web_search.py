"""Tavily-backed web search helper."""

import os

from tavily import TavilyClient


def _build_clients() -> list[TavilyClient]:
    combined_keys = [
        key.strip()
        for key in os.environ.get("TAVILY_API_KEYS", "").split(",")
        if key.strip()
    ]
    legacy_keys = [
        os.environ.get("TAVILY_API_KEY", "").strip(),
        os.environ.get("TAVILY_API_KEY2", "").strip(),
        os.environ.get("TAVILY_API_KEY3", "").strip(),
    ]
    keys = combined_keys or [key for key in legacy_keys if key]
    return [TavilyClient(api_key=key) for key in keys]


tavily_clients: list[TavilyClient] = _build_clients()
_last_search_result: str | None = None


def get_last_search_result() -> str | None:
    return _last_search_result


def reset_last_search_result() -> None:
    global _last_search_result
    _last_search_result = None


def web_search(query: str) -> str:
    """Run Tavily web search and return formatted snippets."""
    global _last_search_result

    if not tavily_clients:
        return "Web検索機能は現在利用できません（APIキー未設定）"

    for client in tavily_clients:
        try:
            results = client.search(query=query, max_results=3, search_depth="basic")
            results_str = str(results).lower()
            if "usage limit" in results_str or "exceeds your plan" in results_str:
                continue

            formatted_results = []
            for result in results.get("results", []):
                title = result.get("title", "")
                content = result.get("content", "")
                url = result.get("url", "")
                formatted_results.append(f"**{title}**\n{content}\nURL: {url}")

            search_result = "\n\n---\n\n".join(formatted_results) if formatted_results else "検索結果がありませんでした"
            _last_search_result = search_result
            return search_result
        except Exception as exc:
            error_str = str(exc).lower()
            if "rate limit" in error_str or "429" in error_str or "quota" in error_str or "usage limit" in error_str:
                continue
            return f"検索エラー: {exc}"

    return "現在、利用殺到でみのるんの検索API無料枠が枯渇したようです。修正をお待ちください"
