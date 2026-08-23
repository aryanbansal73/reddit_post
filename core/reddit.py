"""Reddit fetching over public Atom feeds.

History of this module: v1 drove a headless Chrome and logged in with a real
password. v2 used praw against the OAuth Data API. As of 2026 Reddit gates new
Data API apps behind a request form that names a *moderation* use case, and
`prefs/apps` will not self-serve a script app, so OAuth is not obtainable for
this project. Unauthenticated `.json` endpoints now return 403.

The `.rss` feeds still serve publicly and carry everything needed:

    /r/<sub>/top/.rss?t=week    -> listing, each entry with the full self-text
    <permalink>.rss             -> entry[0] is the post, entries[1:] are comments

So this needs no credentials at all -- no client id, no secret, no app.

What is lost relative to the API: scores, NSFW/stickied flags, and reliable
comment sorting. Posts are therefore filtered on length and title alone.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

from . import config
from .text import censor_profanity, clean_body, strip_emojis

ATOM = {"a": "http://www.w3.org/2005/Atom"}
BASE = "https://www.reddit.com"
_last_request = 0.0


@dataclass
class Post:
    id: str
    subreddit: str
    title: str
    body: str
    url: str
    comments: list[str] = field(default_factory=list)

    @property
    def narration(self) -> str:
        if self.comments:
            return "\n\n".join(self.comments)
        return self.body


class RedditError(RuntimeError):
    pass


RETRYABLE = (429, 500, 502, 503, 504)


def _get(url: str, attempts: int = 5) -> str:
    """Fetch a feed, rate-limited and retried.

    Reddit throttles the feeds aggressively and a 429 needs a real cooldown --
    a few seconds is not enough, and a daily batch walks several subreddits in
    a row. Honour Retry-After when given, otherwise back off exponentially.
    """
    global _last_request
    for attempt in range(attempts):
        gap = time.monotonic() - _last_request
        if gap < config.REDDIT_MIN_INTERVAL:
            time.sleep(config.REDDIT_MIN_INTERVAL - gap)
        _last_request = time.monotonic()

        response = requests.get(
            url, headers={"User-Agent": config.REDDIT_USER_AGENT}, timeout=20
        )
        if response.status_code == 200:
            return response.text

        if response.status_code == 403:
            raise RedditError(
                f"Reddit returned 403 for {url}. The feed is blocked for this IP, "
                f"or the subreddit is private/quarantined."
            )
        if response.status_code not in RETRYABLE or attempt == attempts - 1:
            raise RedditError(
                f"Reddit returned {response.status_code} for {url}"
                + (
                    " -- rate limited. Raise REDDIT_MIN_INTERVAL or run the batch "
                    "over fewer subreddits."
                    if response.status_code == 429
                    else ""
                )
            )

        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.0
        time.sleep(max(delay, config.REDDIT_BACKOFF_BASE * (2 ** attempt)))
    raise RedditError(f"giving up on {url} after {attempts} attempts")


_BLOCK_END = re.compile(r"</(p|div|li|blockquote|h[1-6])>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def _html_to_text(markup: str) -> str:
    """Atom <content> is escaped HTML; unescape it and flatten to plain text."""
    text = html.unescape(markup or "")
    text = _BLOCK_END.sub("\n", text)
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG.sub("", text)
    return html.unescape(text).strip()


def _entry_text(entry: ET.Element) -> str:
    node = entry.find("a:content", ATOM)
    return _html_to_text(node.text if node is not None else "")


def _normalise_title(title: str) -> str:
    """Clean and end-punctuate a title.

    The title is narrated and burned onto the title card, so it needs the same
    profanity pass as the body -- otherwise it lands in the thumbnail and the
    output filename uncensored.
    """
    title = censor_profanity(strip_emojis(title))
    title = re.sub(r"\s+", " ", title.replace("&", " and ")).strip()
    if not title.endswith((".", "!", "?", ";", ":")):
        title += "."
    return title


def _post_id(permalink: str) -> str:
    match = re.search(r"/comments/([a-z0-9]+)", permalink)
    return match.group(1) if match else permalink.rstrip("/").rsplit("/", 1)[-1]


def _subreddit_of(permalink: str) -> str:
    match = re.search(r"/r/([^/]+)/", permalink)
    return match.group(1) if match else "reddit"


# --------------------------------------------------------------------------- #
# single post
# --------------------------------------------------------------------------- #

def fetch_post(url_or_id: str, want_comments: bool | None = None) -> Post:
    """Fetch one post (and its comments) by permalink or id."""
    url_or_id = url_or_id.strip()
    if url_or_id.startswith("http"):
        permalink = url_or_id.split("?")[0].rstrip("/")
    elif "/comments/" in url_or_id:
        permalink = f"{BASE}/{url_or_id.strip('/')}"
    else:
        permalink = f"{BASE}/comments/{url_or_id}"

    feed = _get(f"{permalink}/.rss?sort=top")
    try:
        root = ET.fromstring(feed)
    except ET.ParseError as exc:
        raise RedditError(f"could not parse the feed for {permalink}") from exc

    entries = root.findall("a:entry", ATOM)
    if not entries:
        raise RedditError(f"no entries in the feed for {permalink}")

    head = entries[0]
    link = head.find("a:link", ATOM)
    real_url = link.get("href") if link is not None else permalink
    title = (head.find("a:title", ATOM).text or "").strip()
    body = clean_body(_entry_text(head))
    subreddit = _subreddit_of(real_url)

    if want_comments is None:
        want_comments = subreddit.lower() == "askreddit" or len(body) < 200

    comments: list[str] = []
    if want_comments:
        for entry in entries[1:]:
            text = clean_body(_entry_text(entry))
            if len(text) < 60 or text in ("[removed]", "[deleted]"):
                continue
            comments.append(text)
            if len(comments) >= config.MAX_COMMENTS:
                break

    post = Post(
        id=_post_id(real_url),
        subreddit=subreddit,
        title=_normalise_title(title),
        body=body,
        url=real_url,
        comments=comments,
    )
    if not post.narration:
        raise RedditError(
            "That post has no usable text. Pick a self-post, not a link or image post."
        )
    return post


# --------------------------------------------------------------------------- #
# batch
# --------------------------------------------------------------------------- #

def _usable(title: str, body: str) -> bool:
    if "update" in title.lower():
        return False
    return config.MIN_POST_CHARS <= len(body) <= config.MAX_POST_CHARS


def fetch_batch(
    subreddits: list[str] | None = None,
    per_subreddit: int | None = None,
    time_filter: str = "week",
) -> list[Post]:
    """Top posts across the configured subreddits, for the daily run.

    The listing feed already carries each post's full self-text, so a whole
    batch costs one request per subreddit unless comments are needed.
    """
    subreddits = subreddits or config.DAILY_SUBREDDITS
    per_subreddit = per_subreddit or config.DAILY_POSTS_PER_SUB

    posts: list[Post] = []
    for name in subreddits:
        feed = _get(f"{BASE}/r/{name}/top/.rss?t={time_filter}")
        try:
            root = ET.fromstring(feed)
        except ET.ParseError:
            continue

        wants_comments = name.lower() == "askreddit"
        taken = 0
        for entry in root.findall("a:entry", ATOM):
            if taken >= per_subreddit:
                break
            link = entry.find("a:link", ATOM)
            if link is None:
                continue
            url = link.get("href", "")
            title = (entry.find("a:title", ATOM).text or "").strip()
            body = clean_body(_entry_text(entry))

            if wants_comments:
                try:
                    post = fetch_post(url, want_comments=True)
                except RedditError:
                    continue
                if not post.narration:
                    continue
            else:
                if not _usable(title, body):
                    continue
                post = Post(
                    id=_post_id(url),
                    subreddit=name,
                    title=_normalise_title(title),
                    body=body,
                    url=url,
                )
            posts.append(post)
            taken += 1
    return posts
