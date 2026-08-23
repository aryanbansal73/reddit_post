"""Text cleanup, sentence splitting and caption chunking.

Replaces the scattered helpers that used to live in scrapeLinksHelpers.py and
support_func.py. The `demoji` dependency is gone -- a codepoint-range regex does
the same job without downloading an emoji table at runtime.
"""
import html
import re

# Emoji, pictographs, transport, flags, dingbats, variation selectors.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0001F900-\U0001F9FF]+",
    flags=re.UNICODE,
)

# TTS reads these literally and it sounds wrong; spell them out instead.
# Expansions run after censor_profanity, so they must already be clean --
# otherwise "TIFU" would smuggle the f-word past the filter into the narration.
_ABBREVIATIONS = {
    r"\bAITA\b": "Am I the asshole",
    r"\bTIFU\b": "Today I messed up",
    r"\bNTA\b": "Not the asshole",
    r"\bYTA\b": "You're the asshole",
    r"\bOP\b": "O P",
    r"\bSO\b": "significant other",
    r"\bAFAIK\b": "as far as I know",
    r"\bIMO\b": "in my opinion",
    r"\bTL;?DR\b": "To be brief",
    r"\bF\.?Y\.?I\.?\b": "F Y I",
}

# Kept from the original so uploads stay monetisable, but split into two rules.
#
# The original did a plain str.replace per word, which mangled innocent words
# ("cocktail" -> "rodtail"). A pure whole-word regex fixes that but then misses
# every inflection, and "fucked"/"fucking" are far more common in these
# subreddits than the bare stem. So: stems that inflect keep their suffix,
# everything else must match as a whole word.
_INFLECTED = {"fuck": "frick", "shit": "crap", "bitch": "dog"}
_EXACT = {
    "shitty": "lousy",   # listed first below so it wins over the "shit" stem
    "damn": "darn",      # whole-word only, or "damnation" -> "darnation"
    "whore": "tramp",
    "bastard": "scoundrel",
    "cock": "rod",       # whole-word only, or "cocktail" -> "rodtail"
}
_PROFANITY_RE = re.compile(
    r"\b(shitty|" + "|".join(f"{s}\\w*" for s in _INFLECTED) + "|"
    + "|".join(w for w in _EXACT if w != "shitty") + r")\b",
    re.IGNORECASE,
)

# A trailing "EDIT:" / "UPDATE:" block is author commentary, not story.
_TRAILER_RE = re.compile(
    r"^\s*(edit(ed)?( to add)?|update( post)?|tl;?dr)\s*[:\-]", re.IGNORECASE | re.MULTILINE
)

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])[\s ]+")
_ABBREV_GUARD_RE = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|i\.e|e\.g)\.$", re.I)


def strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def censor_profanity(text: str) -> str:
    def _sub(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        if lower in _EXACT:
            clean = _EXACT[lower]
        else:
            for stem, replacement in _INFLECTED.items():
                if lower.startswith(stem):
                    clean = replacement + lower[len(stem):]
                    break
            else:
                return word
        return clean.capitalize() if word[0].isupper() else clean

    return _PROFANITY_RE.sub(_sub, text)


def expand_abbreviations(text: str) -> str:
    """Expand acronyms before synthesis so the voice says them properly."""
    for pattern, replacement in _ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)
    return text


def trim_trailers(text: str, min_keep_ratio: float = 0.25) -> str:
    """Drop a trailing EDIT/UPDATE block, but never gut the whole post.

    The original ran four near-identical regex passes with slightly different
    guards. One pass over all matches is equivalent and honours the same rule:
    only cut if enough of the story survives.
    """
    cut = len(text)
    for match in _TRAILER_RE.finditer(text):
        if match.start() >= len(text) * min_keep_ratio:
            cut = min(cut, match.start())
            break
    return text[:cut].strip()


def clean_body(raw: str) -> str:
    """Full cleanup for a scraped post body."""
    text = html.unescape(raw)
    text = strip_emojis(text)
    text = trim_trailers(text)
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return censor_profanity(text).strip()


def split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries, keeping common abbreviations intact."""
    parts, buffer = [], ""
    for chunk in _SENTENCE_END_RE.split(text):
        candidate = f"{buffer} {chunk}".strip() if buffer else chunk.strip()
        if _ABBREV_GUARD_RE.search(candidate):
            buffer = candidate
            continue
        buffer = ""
        if candidate:
            parts.append(candidate)
    if buffer:
        parts.append(buffer)
    return parts


def chunk_for_captions(sentence: str, max_chars: int = 15) -> list[str]:
    """Break a sentence into on-screen caption groups of a few words."""
    chunks, current = [], ""
    for word in sentence.split():
        if current and len(current) + len(word) + 1 > max_chars:
            chunks.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        chunks.append(current)
    return chunks


def estimate_syllables(word: str) -> int:
    """Cheap syllable count, used to weight caption timing inside a sentence.

    Not linguistically exact -- it only has to beat character count, which it
    comfortably does for distributing a known sentence duration across words.
    """
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 1
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and not word.endswith(("le", "ee", "ye")) and count > 1:
        count -= 1
    return max(1, count)


def slugify_title(title: str, max_chars: int = 40) -> str:
    """Filesystem-safe stub of a post title, for output filenames."""
    slug = re.sub(r"[^\w\s-]", "", title).strip()
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug[:max_chars].strip("_") or "post"


def wrap_text(text: str, line_length: int = 34) -> str:
    """Greedy word wrap. drawtext honours real newlines from a textfile."""
    lines, current = [], ""
    for word in text.split():
        if current and len(current) + len(word) + 1 > line_length:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "\n".join(lines)
