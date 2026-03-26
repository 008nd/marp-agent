"""Tweet URL generator."""

import urllib.parse

_generated_tweet_url: str | None = None


def get_generated_tweet_url() -> str | None:
    return _generated_tweet_url


def reset_generated_tweet_url() -> None:
    global _generated_tweet_url
    _generated_tweet_url = None


def generate_tweet_url(tweet_text: str) -> str:
    """Generate a tweet intent URL for the given text."""
    global _generated_tweet_url
    encoded_text = urllib.parse.quote(tweet_text, safe="")
    _generated_tweet_url = f"https://twitter.com/intent/tweet?text={encoded_text}"
    return "ツイートURLを生成しました。"
