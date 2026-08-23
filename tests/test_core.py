"""Unit tests for the parts that do not need ffmpeg, Reddit or a voice model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import render, text  # noqa: E402
from core.tts import Caption, _captions_for_sentence  # noqa: E402


# --- text -------------------------------------------------------------------

def test_strip_emojis():
    assert text.strip_emojis("hello 👋 world 🎉") == "hello  world "


def test_censor_profanity_preserves_case_and_word_boundary():
    assert text.censor_profanity("Damn it") == "Darn it"
    assert text.censor_profanity("damnation") == "damnation"  # not a whole word


def test_censor_profanity_catches_inflections():
    """The common forms in these subreddits are inflected, not the bare stem."""
    assert text.censor_profanity("I fucked up") == "I fricked up"
    assert text.censor_profanity("fucking hell") == "fricking hell"
    assert text.censor_profanity("Fucked") == "Fricked"
    assert text.censor_profanity("shits") == "craps"


def test_censor_profanity_leaves_innocent_words_alone():
    """The original str.replace turned 'cocktail' into 'rodtail'."""
    assert text.censor_profanity("a cocktail party") == "a cocktail party"
    assert text.censor_profanity("Scunthorpe") == "Scunthorpe"
    assert text.censor_profanity("shitty day") == "lousy day"  # beats the shit stem


def test_trim_trailers_cuts_late_edit_block():
    body = "A" * 400 + "\nEDIT: thanks for the gold"
    assert "thanks for the gold" not in text.trim_trailers(body)


def test_trim_trailers_keeps_early_edit():
    body = "EDIT: quick note\n" + "A" * 400
    assert text.trim_trailers(body) == body.strip()


def test_split_sentences_handles_abbreviations():
    assert text.split_sentences("I saw Dr. Smith. He left.") == [
        "I saw Dr. Smith.", "He left."
    ]


def test_chunk_for_captions_respects_max_chars():
    for chunk in text.chunk_for_captions("the quick brown fox jumps over", 15):
        assert len(chunk) <= 15


def test_estimate_syllables():
    assert text.estimate_syllables("strength") == 1
    assert text.estimate_syllables("banana") == 3
    assert text.estimate_syllables("make") == 1


def test_wrap_text_never_exceeds_width():
    wrapped = text.wrap_text("a bb ccc dddd eeeee ffffff", 10)
    assert all(len(line) <= 10 for line in wrapped.split("\n"))


def test_slugify_title_is_filesystem_safe():
    slug = text.slugify_title('AITA for "this"? / that\\')
    assert "/" not in slug and "\\" not in slug and '"' not in slug


# --- caption timing ---------------------------------------------------------

def test_captions_cover_exactly_the_sentence_duration():
    captions = _captions_for_sentence("the quick brown fox jumps high", 10.0, 4.0)
    assert captions[0].start == 10.0
    assert abs(captions[-1].end - 14.0) < 1e-9
    for earlier, later in zip(captions, captions[1:]):
        assert abs(earlier.end - later.start) < 1e-9  # contiguous, no gaps


def test_longer_chunks_get_more_time():
    captions = _captions_for_sentence("hi banana banana banana", 0.0, 4.0)
    spans = [c.end - c.start for c in captions]
    assert max(spans) > min(spans)


# --- part planning ----------------------------------------------------------

def _captions(count: int, each: float = 2.0) -> list[Caption]:
    return [Caption(f"c{i}", i * each, (i + 1) * each) for i in range(count)]


def test_plan_parts_single_part_when_short():
    spans = render.plan_parts(_captions(10), title_duration=4.0)  # 20s narration
    assert spans == [(0.0, 20.0)]


def test_plan_parts_splits_long_narration():
    spans = render.plan_parts(_captions(60), title_duration=5.0)  # 120s narration
    assert len(spans) > 1
    budget = render.config.MAX_SHORT_SECONDS - 5.0
    assert all(end - start <= budget + 1e-6 for start, end in spans)


def test_no_part_ever_exceeds_the_budget():
    """Regression: the final part used to absorb the tail and bust the cap."""
    for count in range(2, 90):
        for title in (2.0, 3.52, 8.0):
            budget = render.config.MAX_SHORT_SECONDS - title
            spans = render.plan_parts(_captions(count), title_duration=title)
            for start, end in spans:
                assert end - start <= budget + 1e-6, (
                    f"{count} captions, title {title}s -> part of {end - start:.2f}s "
                    f"exceeds budget {budget:.2f}s"
                )


def test_plan_parts_is_contiguous_and_complete():
    captions = _captions(60)
    spans = render.plan_parts(captions, title_duration=5.0)
    assert spans[0][0] == 0.0
    assert abs(spans[-1][1] - captions[-1].end) < 1e-9
    for earlier, later in zip(spans, spans[1:]):
        assert earlier[1] == later[0]


def test_plan_parts_never_leaves_a_stub_tail():
    """A 58s part plus a 4s part should be two balanced ~31s parts instead."""
    for count in range(2, 90):
        for title in (2.0, 3.52, 8.0):
            spans = render.plan_parts(_captions(count), title_duration=title)
            if len(spans) < 2:
                continue
            lengths = [end - start for start, end in spans]
            assert min(lengths) > 10, f"{count} captions -> stub part {min(lengths):.1f}s"
            # Parts should be roughly even, not front-loaded.
            assert max(lengths) / min(lengths) < 2.0


def test_plan_parts_rejects_title_that_eats_the_budget():
    try:
        render.plan_parts(_captions(10), title_duration=58.0)
    except render.RenderError:
        return
    raise AssertionError("expected RenderError for an over-long title")


# --- ASS generation ---------------------------------------------------------

def test_write_ass_rebases_onto_part_timeline(tmp_path):
    captions = _captions(30)  # 0..60s
    out = tmp_path / "part.ass"
    render.write_ass(out, "A title.", 3.0, captions, span=(20.0, 40.0))
    dialogues = [l for l in out.read_text().splitlines() if l.startswith("Dialogue")]
    caption_lines = [l for l in dialogues if ",Caption," in l]

    # Only the 10 captions inside 20..40s survive, and none from outside it.
    assert len(caption_lines) == 10
    assert all(f"c{i}" not in "".join(caption_lines) for i in list(range(10)) + [20, 29])
    # The first in-span caption (narration t=20) lands at title_duration + 0.
    assert caption_lines[0].split(",")[1] == "0:00:03.00"
    # The last ends at title_duration + span length = 3 + 20 = 23s.
    assert caption_lines[-1].split(",")[2] == "0:00:23.00"


def test_write_ass_escapes_brace_injection(tmp_path):
    out = tmp_path / "x.ass"
    render.write_ass(out, "Title {\\an8} hack", 2.0, _captions(2), span=(0.0, 4.0))
    body = out.read_text()
    assert "\\{" in body and "\\}" in body


def test_font_family_reads_the_ttf_name_table():
    assert render.font_family(render.config.CAPTION_FONT) == "Gill Sans MT"
    assert render.font_family(render.config.TITLE_FONT) == "Arial Rounded MT Bold"


# --- regressions ------------------------------------------------------------

def test_abbreviation_expansions_are_already_censored():
    """Expansions run after censor_profanity, so they must not reintroduce it."""
    for expansion in text._ABBREVIATIONS.values():
        assert text.censor_profanity(expansion) == expansion


def test_title_normalisation_censors_and_punctuates():
    from core.reddit import _normalise_title
    assert _normalise_title("Damn me & you") == "Darn me and you."
    assert _normalise_title("Already ends?") == "Already ends?"


# --- reddit feed parsing (offline) ------------------------------------------

from core import reddit as _reddit  # noqa: E402

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <link href="https://www.reddit.com/r/tifu/comments/abc123/some_slug/"/>
    <title>TIFU by testing &amp; parsing</title>
    <content type="html">&lt;div&gt;&lt;p&gt;First para.&lt;/p&gt;&lt;p&gt;Second &lt;a href="http://x.co"&gt;para&lt;/a&gt;.&lt;/p&gt;&lt;/div&gt;</content>
  </entry>
  <entry>
    <link href="https://www.reddit.com/r/tifu/comments/abc123/some_slug/c1/"/>
    <title>/u/someone on TIFU by testing</title>
    <content type="html">&lt;p&gt;A comment long enough to survive the sixty character minimum filter here.&lt;/p&gt;</content>
  </entry>
</feed>"""


def test_html_to_text_flattens_blocks_and_drops_tags():
    text = _reddit._html_to_text(
        "&lt;p&gt;One.&lt;/p&gt;&lt;p&gt;Two&lt;br/&gt;three.&lt;/p&gt;"
    )
    assert "<" not in text and ">" not in text
    assert "One." in text and "Two" in text and "three." in text


def test_post_id_and_subreddit_from_permalink():
    url = "https://www.reddit.com/r/AmItheAsshole/comments/1vu4oua/some_slug/"
    assert _reddit._post_id(url) == "1vu4oua"
    assert _reddit._subreddit_of(url) == "AmItheAsshole"


def test_feed_entry_yields_title_and_body(monkeypatch):
    monkeypatch.setattr(_reddit, "_get", lambda url, attempts=5: _FEED)
    post = _reddit.fetch_post("https://www.reddit.com/r/tifu/comments/abc123/some_slug/")
    assert post.id == "abc123"
    assert post.subreddit == "tifu"
    assert post.title == "TIFU by testing and parsing."   # & expanded, punctuated
    assert "First para." in post.body and "Second" in post.body
    assert "http" not in post.body                        # link stripped by clean_body


def test_comments_are_collected_when_asked(monkeypatch):
    monkeypatch.setattr(_reddit, "_get", lambda url, attempts=5: _FEED)
    post = _reddit.fetch_post("https://reddit.com/r/tifu/comments/abc123/s/", want_comments=True)
    assert len(post.comments) == 1
    assert post.narration == post.comments[0]             # comments win over body


def test_get_raises_a_useful_error_on_rate_limit(monkeypatch):
    class Resp:
        status_code = 429
        headers: dict = {}
        text = ""

    monkeypatch.setattr(_reddit.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(_reddit.time, "sleep", lambda s: None)
    try:
        _reddit._get("https://example.com/x.rss", attempts=2)
    except _reddit.RedditError as exc:
        assert "rate limited" in str(exc)
        return
    raise AssertionError("expected RedditError on 429")
