import argparse
import http.cookiejar
import itertools
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone

import requests

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi, CouldNotRetrieveTranscript

from agent_utils import load_config

_FALLBACK_OUT_DIR = '~/scm-coe/raw/transcripts/podcast'


class Spinner:
    def __init__(self, message):
        self._message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        for frame in itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'):
            if self._stop.is_set():
                break
            sys.stdout.write(f'\r{self._message} {frame}')
            sys.stdout.flush()
            time.sleep(0.1)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        sys.stdout.write(f'\r{self._message} done\n')
        sys.stdout.flush()


class YouTubeService:
    """Wraps YouTube Data API v3 for playlist/video metadata."""

    def __init__(self, api_key: str):
        self._svc = build('youtube', 'v3', developerKey=api_key)

    def get_latest_playlist_videos(self, playlist_id: str, count: int = 3) -> list[dict]:
        """Fetch all items (paginated) and return the `count` most recently published.

        Playlist order from the API is insertion order, not chronological, so a
        newly added episode can land anywhere in the list -- pagination is required
        to find the true most-recent items, not just the first page.
        """
        items = []
        page_token = None
        while True:
            try:
                resp = self._svc.playlistItems().list(
                    part='snippet,contentDetails',
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                raise RuntimeError(f'YouTube API error fetching playlist {playlist_id}: {e.status_code} {e.reason}') from e

            items.extend(resp.get('items', []))
            page_token = resp.get('nextPageToken')
            if not page_token:
                break

        if not items:
            raise RuntimeError(f'No videos found in playlist: {playlist_id}')

        def _date(item):
            return (
                item.get('contentDetails', {}).get('videoPublishedAt')
                or item.get('snippet', {}).get('publishedAt', '')
            )

        sorted_items = sorted(items, key=_date, reverse=True)[:count]
        video_ids = [item['snippet']['resourceId']['videoId'] for item in sorted_items]
        durations = self._get_durations(video_ids)
        return [
            {
                'id': item['snippet']['resourceId']['videoId'],
                'title': item['snippet']['title'],
                'published_at': _date(item),
                'duration_seconds': durations.get(item['snippet']['resourceId']['videoId']),
            }
            for item in sorted_items
        ]

    def _get_durations(self, video_ids: list[str]) -> dict[str, int | None]:
        """Batch-fetch durations (in seconds) for up to 50 video IDs."""
        if not video_ids:
            return {}
        try:
            resp = self._svc.videos().list(
                part='contentDetails',
                id=','.join(video_ids),
            ).execute()
        except HttpError as e:
            raise RuntimeError(f'YouTube API error fetching durations: {e.status_code} {e.reason}') from e

        return {
            item['id']: _parse_duration_seconds(item['contentDetails']['duration'])
            for item in resp.get('items', [])
        }

    def get_video_info(self, video_id: str) -> dict:
        """Return title, published_at, and duration for a single video."""
        try:
            resp = self._svc.videos().list(
                part='snippet,contentDetails',
                id=video_id,
            ).execute()
        except HttpError as e:
            raise RuntimeError(f'YouTube API error fetching video {video_id}: {e.status_code} {e.reason}') from e

        items = resp.get('items', [])
        if not items:
            raise RuntimeError(f'Video not found: {video_id}')
        snippet = items[0]['snippet']
        duration = items[0]['contentDetails']['duration']
        return {
            'id': video_id,
            'title': snippet['title'],
            'published_at': snippet['publishedAt'],
            'duration_seconds': _parse_duration_seconds(duration),
        }


def _get_api_key() -> str:
    key = os.getenv('YOUTUBE_API_KEY', '')
    if not key:
        raise RuntimeError('YOUTUBE_API_KEY is not set. Add it to your .env file.')
    return key


def _get_fetch_count() -> int:
    return int(os.getenv('PODCAST_FETCH_COUNT', '3'))


def _playlist_id(url_or_id: str) -> str:
    """Extract playlist ID from a full URL or return as-is if already an ID."""
    m = re.search(r'[?&]list=([^&]+)', url_or_id)
    return m.group(1) if m else url_or_id


def _video_id(url_or_id: str) -> str:
    """Extract video ID from a watch URL or return as-is if already an ID."""
    m = re.search(r'(?:v=|youtu\.be/)([^&?/]+)', url_or_id)
    if not m:
        raise ValueError(f'Could not extract video ID from: {url_or_id}')
    return m.group(1)


def _format_date(published_at: str) -> str:
    """Convert ISO 8601 timestamp to YYYY-MM-DD."""
    if not published_at:
        return ''
    try:
        dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d')
    except ValueError:
        return published_at[:10]


_DURATION_RE = re.compile(r'P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')

_SHORT_MAX_SECONDS = 180


def _parse_duration_seconds(duration: str) -> int | None:
    """Convert an ISO 8601 duration (e.g. 'PT4M13S') to whole seconds."""
    m = _DURATION_RE.fullmatch(duration)
    if not m:
        return None
    hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def _format_label(duration_seconds: int | None) -> str:
    """Classify a video as a Short or a full episode based on its duration."""
    if duration_seconds is not None and duration_seconds <= _SHORT_MAX_SECONDS:
        return 'Short clip / excerpt'
    return 'episode'


def _format_duration_clock(duration_seconds: int | None) -> str:
    """Render a duration in seconds as m:ss or h:mm:ss."""
    if duration_seconds is None:
        return ''
    hours, rem = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{seconds:02d}'
    return f'{minutes}:{seconds:02d}'


def _yaml_quote(value: str) -> str:
    """Wrap a string in double quotes for a YAML frontmatter value, escaping embedded quotes."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _build_frontmatter(date_str: str, source_url: str, podcast_name: str, duration_seconds: int | None) -> str:
    lines = [
        '---',
        f'podcastDate: {date_str}',
        f'source: {source_url}',
        f'podcast: {_yaml_quote(podcast_name)}',
        'description: ""',
        f'format: {_yaml_quote(_format_label(duration_seconds))}',
        f'duration: {_yaml_quote(_format_duration_clock(duration_seconds))}',
        '---',
        '',
    ]
    return '\n'.join(lines)


def _get_out_dir():
    return os.path.expanduser(os.getenv('PODCAST_OUTPUT_DIR', _FALLBACK_OUT_DIR))


def load_playlists():
    return load_config().get('podcast_playlists', [])


def _build_http_client() -> requests.Session | None:
    path = os.getenv('YOUTUBE_COOKIES_FILE', '')
    if not path:
        return None
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        print(f'Warning: YOUTUBE_COOKIES_FILE not found at {expanded}, proceeding without cookies.', flush=True)
        return None
    jar = http.cookiejar.MozillaCookieJar(expanded)
    jar.load(ignore_discard=True, ignore_expires=True)
    session = requests.Session()
    session.cookies = jar
    return session


def get_transcript(video_id):
    client = _build_http_client()
    api = YouTubeTranscriptApi(http_client=client) if client else YouTubeTranscriptApi()
    try:
        return api.fetch(video_id)
    except CouldNotRetrieveTranscript:
        transcript_list = api.list(video_id)
        return next(iter(transcript_list)).fetch()


def format_transcript(transcript):
    lines = []
    for snippet in transcript:
        text = re.sub(r'<[^>]+>', '', snippet.text).strip()
        if text:
            lines.append(text)
    return ' '.join(lines)


def safe_filename(title):
    name = re.sub(r'[^\w\s\-]', '', title).strip()
    return re.sub(r'\s+', ' ', name)


def _fetch_playlist_videos(playlist_name: str, playlist_url: str, count: int) -> list[dict]:
    """Fetch up to `count` most-recent video entries from a playlist."""
    svc = YouTubeService(_get_api_key())
    with Spinner(f'[{playlist_name}] Fetching playlist info...'):
        videos = svc.get_latest_playlist_videos(_playlist_id(playlist_url), count=count)
    print(f'[{playlist_name}] Found {len(videos)} video(s).', flush=True)
    return videos


def _process_video_entry(playlist_name: str, video: dict, out_dir: str, add_delay: bool = False) -> None:
    """Fetch and save transcript for a single video entry."""
    video_id = video['id']
    title = video['title']
    date_str = _format_date(video['published_at'])
    filename = os.path.join(out_dir, f'{safe_filename(title)}.md')

    print(f'[{playlist_name}] {title}', flush=True)

    if os.path.exists(filename):
        print(f'[{playlist_name}]   Skipped (already exists)', flush=True)
        return

    if add_delay:
        time.sleep(3)

    try:
        with Spinner(f'[{playlist_name}]   Fetching transcript...'):
            transcript = get_transcript(video_id)
        body = format_transcript(transcript)
    except Exception as e:  # pylint: disable=broad-except
        print(f'[{playlist_name}]   Transcript error: {e}', flush=True)
        return

    source_url = f'https://www.youtube.com/watch?v={video_id}'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(_build_frontmatter(date_str, source_url, playlist_name, video.get('duration_seconds')))
        f.write('\n')
        f.write(body)
        f.write('\n')

    print(f'[{playlist_name}]   Saved to {filename}', flush=True)


def process_video(video_url, name, out_dir):
    vid_id = _video_id(video_url)
    svc = YouTubeService(_get_api_key())

    with Spinner(f'[{name}] Fetching video info...'):
        video = svc.get_video_info(vid_id)

    title = video['title']
    date_str = _format_date(video['published_at'])

    print(f'[{name}] Title: {title}', flush=True)
    print(f'[{name}] Video ID: {vid_id}', flush=True)

    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, f'{safe_filename(title)}.md')

    if os.path.exists(filename):
        print(f'[{name}] Skipped (already exists): {filename}', flush=True)
        return

    with Spinner(f'[{name}] Fetching transcript...'):
        transcript = get_transcript(vid_id)
    body = format_transcript(transcript)

    source_url = f'https://www.youtube.com/watch?v={vid_id}'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(_build_frontmatter(date_str, source_url, name, video.get('duration_seconds')))
        f.write('\n')
        f.write(body)
        f.write('\n')

    print(f'[{name}] Saved to {filename}', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Fetch recent podcast transcripts from YouTube playlists.')
    parser.add_argument('--playlist', help='Single playlist URL or ID to process (overrides settings.json)')
    parser.add_argument('--video', help='Single video URL or ID to fetch transcript for')
    parser.add_argument('--name', default='Podcast', help='Name for the playlist/video when using --playlist or --video')
    parser.add_argument('--out', default=_get_out_dir(), help='Output directory (default: ~/scm-coe/raw/transcripts/podcast)')
    args = parser.parse_args()

    if args.video:
        process_video(args.video, args.name, args.out)
        return

    if args.playlist:
        fetch_count = _get_fetch_count()
        videos = _fetch_playlist_videos(args.name, args.playlist, fetch_count)
        os.makedirs(args.out, exist_ok=True)
        for i, video in enumerate(videos):
            _process_video_entry(args.name, video, args.out, add_delay=(i > 0))
        return

    playlists = load_playlists()
    if not playlists:
        print('No playlists found in settings.json. Use --playlist to specify one.', flush=True)
        return

    fetch_count = _get_fetch_count()
    print(f'Processing {len(playlists)} playlist(s), {fetch_count} episode(s) each...', flush=True)

    # Phase 1: fetch video lists for all playlists up front
    playlist_videos = []
    for entry in playlists:
        try:
            videos = _fetch_playlist_videos(entry['name'], entry['url'], fetch_count)
            playlist_videos.append((entry['name'], videos))
        except Exception as e:  # pylint: disable=broad-except
            print(f'[{entry["name"]}] Error fetching playlist: {e}', flush=True)

    # Phase 2: round-robin by episode position (newest first across all playlists, then second newest, etc.)
    os.makedirs(args.out, exist_ok=True)
    first_transcript = True
    for i in range(fetch_count):
        for name, videos in playlist_videos:
            if i >= len(videos):
                continue
            try:
                _process_video_entry(name, videos[i], args.out, add_delay=not first_transcript)
                first_transcript = False
            except Exception as e:  # pylint: disable=broad-except
                print(f'[{name}] Error processing episode {i + 1}: {e}', flush=True)

    print('\nAll done.', flush=True)


if __name__ == '__main__':
    main()
