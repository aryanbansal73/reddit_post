"""Reddit fetching over the official OAuth API.

Replaces ~400 lines of Selenium that logged in with a real password, drove a
headless Chrome and parsed obfuscated CSS class names. The same data is public
over the API with a free "script" app, no browser and no credentials beyond a
client id/secret.
"""
import re
from dataclasses import dataclass

import praw

from . import config
from .text import censor_profanity, clean_body, strip_emojis


@dataclass
class Post:
    id: str
    subreddit: str
    title: str
    body: str
    url: str
    comments: list[str]

    @property
    def narration(self) -> str:
        if self.comments:
            return "\n\n".join(self.comments)
        return self.body


class RedditError(RuntimeError):
    pass


def _client() -> praw.Reddit:
    if not config.REDDIT_CLIENT_ID or not config.REDDIT_CLIENT_SECRET:
        raise RedditError(
            "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are unset. Create a free "
            "'script' app at https://www.reddit.com/prefs/apps"
        )
    return praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT,
        check_for_async=False,
    )


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


def _top_comments(submission, limit: int) -> list[str]:
    submission.comment_sort = "top"
    submission.comments.replace_more(limit=0)
    out = []
    for comment in submission.comments[: limit * 3]:
        body = clean_body(getattr(comment, "body", ""))
        if len(body) < 40 or body in ("[removed]", "[deleted]"):
            continue
        out.append(body)
        if len(out) >= limit:
            break
    return out


def _to_post(submission, want_comments: bool) -> Post:
    return Post(
        id=submission.id,
        subreddit=str(submission.subreddit),
        title=_normalise_title(submission.title),
        body=clean_body(submission.selftext or ""),
        url=f"https://reddit.com{submission.permalink}",
        comments=_top_comments(submission, config.MAX_COMMENTS) if want_comments else [],
    )


def fetch_post(url_or_id: str) -> Post:
    """Fetch a single post by permalink or id, for on-demand rendering."""
    reddit = _client()
    if url_or_id.startswith("http") or "/comments/" in url_or_id:
        submission = reddit.submission(url=url_or_id)
    else:
        submission = reddit.submission(id=url_or_id)

    want_comments = str(submission.subreddit).lower() == "askreddit"
    post = _to_post(submission, want_comments)
    if not post.narration:
        raise RedditError(
            "That post has no text body. Pick a self-post, not a link or image post."
        )
    return post


def _is_usable(submission) -> bool:
    if submission.stickied or submission.over_18 or not submission.is_self:
        return False
    if "update" in submission.title.lower():
        return False
    length = len(submission.selftext or "")
    return config.MIN_POST_CHARS <= length <= config.MAX_POST_CHARS


def fetch_batch(
    subreddits: list[str] | None = None,
    per_subreddit: int | None = None,
    time_filter: str = "week",
) -> list[Post]:
    """Top posts of the week across the configured subreddits, for the daily run."""
    reddit = _client()
    subreddits = subreddits or config.DAILY_SUBREDDITS
    per_subreddit = per_subreddit or config.DAILY_POSTS_PER_SUB

    posts: list[Post] = []
    for name in subreddits:
        want_comments = name.lower() == "askreddit"
        taken = 0
        for submission in reddit.subreddit(name).top(time_filter=time_filter, limit=50):
            if taken >= per_subreddit:
                break
            if want_comments:
                if submission.stickied or submission.over_18:
                    continue
            elif not _is_usable(submission):
                continue
            post = _to_post(submission, want_comments)
            if not post.narration:
                continue
            posts.append(post)
            taken += 1
    return posts
