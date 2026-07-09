"""Pure parsing/formatting helpers for YouTube podcast ingestion.

No I/O and no API calls — everything here is deterministic and unit-testable.
"""

import re
from datetime import datetime, timezone

DURATION_RE = re.compile(r'P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')

SHORT_MAX_SECONDS = 180


def playlist_id(url_or_id: str) -> str:
    """Extract playlist ID from a full URL or return as-is if already an ID."""
    m = re.search(r'[?&]list=([^&]+)', url_or_id)
    return m.group(1) if m else url_or_id


def video_id(url_or_id: str) -> str:
    """Extract video ID from a watch URL or return as-is if already an ID."""
    m = re.search(r'(?:v=|youtu\.be/)([^&?/]+)', url_or_id)
    if not m:
        raise ValueError(f'Could not extract video ID from: {url_or_id}')
    return m.group(1)


def format_date(published_at: str) -> str:
    """Convert ISO 8601 timestamp to YYYY-MM-DD."""
    if not published_at:
        return ''
    try:
        dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d')
    except ValueError:
        return published_at[:10]


def parse_duration_seconds(duration: str) -> int | None:
    """Convert an ISO 8601 duration (e.g. 'PT4M13S') to whole seconds."""
    m = DURATION_RE.fullmatch(duration)
    if not m:
        return None
    hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_label(duration_seconds: int | None) -> str:
    """Classify a video as a Short or a full episode based on its duration."""
    if duration_seconds is not None and duration_seconds <= SHORT_MAX_SECONDS:
        return 'Short clip / excerpt'
    return 'episode'


def format_duration_clock(duration_seconds: int | None) -> str:
    """Render a duration in seconds as m:ss or h:mm:ss."""
    if duration_seconds is None:
        return ''
    hours, rem = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{seconds:02d}'
    return f'{minutes}:{seconds:02d}'


def yaml_quote(value: str) -> str:
    """Wrap a string in double quotes for a YAML frontmatter value, escaping embedded quotes."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def build_frontmatter(date_str: str, source_url: str, podcast_name: str,
                      duration_seconds: int | None) -> str:
    """Render the YAML frontmatter block for a transcript markdown file."""
    lines = [
        '---',
        f'podcastDate: {date_str}',
        f'source: {source_url}',
        f'podcast: {yaml_quote(podcast_name)}',
        'description: ""',
        f'format: {yaml_quote(format_label(duration_seconds))}',
        f'duration: {yaml_quote(format_duration_clock(duration_seconds))}',
        '---',
        '',
    ]
    return '\n'.join(lines)


def format_transcript(transcript) -> str:
    """Join transcript snippets into one line of plain text, stripping HTML tags."""
    lines = []
    for snippet in transcript:
        text = re.sub(r'<[^>]+>', '', snippet.text).strip()
        if text:
            lines.append(text)
    return ' '.join(lines)


def safe_filename(title: str) -> str:
    """Reduce a video title to a filesystem-safe filename (drops path separators etc.)."""
    name = re.sub(r'[^\w\s\-]', '', title).strip()
    return re.sub(r'\s+', ' ', name)
