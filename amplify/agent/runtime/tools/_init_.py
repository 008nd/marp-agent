"""Tool helpers used by the OpenAI runtime."""

from .generate_tweet import (
    generate_tweet_url,
    get_generated_tweet_url,
    reset_generated_tweet_url,
)
from .output_slide import (
    build_output_slide_tool_description,
    get_generated_markdown,
    output_slide,
    reset_generated_markdown,
)
from .web_search import (
    get_last_search_result,
    reset_last_search_result,
    tavily_clients,
    web_search,
)

__all__ = [
    "web_search",
    "tavily_clients",
    "get_last_search_result",
    "reset_last_search_result",
    "output_slide",
    "get_generated_markdown",
    "reset_generated_markdown",
    "build_output_slide_tool_description",
    "generate_tweet_url",
    "get_generated_tweet_url",
    "reset_generated_tweet_url",
]
