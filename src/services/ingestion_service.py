"""Podcast ingestion service: YouTube playlists/videos -> transcript markdown files.

Implements the Service Layer for the podcast tool (docs/ARCHITECTURE.md):
- `YouTubeService` is the adapter around the YouTube Data API v3.
- `IngestionService` holds the business logic (what to fetch, dedupe, dry-run,
  round-robin ordering, rate-limit pauses) and file writing.

Presentation (spinners, argparse) stays in src/tools/tool_podcast.py; callers may
pass a `progress` factory — a callable taking a message and returning a context
manager — to show activity during long fetches.
"""

import contextlib
import http.cookiejar
import os
import time

import requests

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi, CouldNotRetrieveTranscript

from agent_utils import load_config
from utils.youtube import (
    build_frontmatter,
    format_date,
    format_transcript,
    parse_duration_seconds,
    playlist_id,
    safe_filename,
    video_id,
)

_FALLBACK_OUT_DIR = '~/scm-coe/raw/transcripts/podcast'


def get_api_key() -> str:
    """Return the YouTube Data API key from the environment."""
    key = os.getenv('YOUTUBE_API_KEY', '')
    if not key:
        raise RuntimeError('YOUTUBE_API_KEY is not set. Add it to your .env file.')
    return key


def get_fetch_count() -> int:
    """Episodes to fetch per playlist (PODCAST_FETCH_COUNT, default 3)."""
    return int(os.getenv('PODCAST_FETCH_COUNT', '3'))


def get_out_dir() -> str:
    """Output directory for transcript files (PODCAST_OUTPUT_DIR or fallback)."""
    return os.path.expanduser(os.getenv('PODCAST_OUTPUT_DIR', _FALLBACK_OUT_DIR))


def load_playlists() -> list[dict]:
    """Return the podcast_playlists entries from settings.json."""
    return load_config().get('podcast_playlists', [])


class TimeoutSession(requests.Session):
    """requests.Session that applies a default timeout so transcript fetches cannot hang forever."""

    def __init__(self, timeout_seconds: float):
        super().__init__()
        self._timeout_seconds = timeout_seconds

    def request(self, *args, **kwargs):
        kwargs.setdefault('timeout', self._timeout_seconds)
        return super().request(*args, **kwargs)


def build_http_client() -> requests.Session:
    """Session with a default timeout, plus YouTube cookies when configured."""
    timeout_seconds = float(os.getenv('PODCAST_HTTP_TIMEOUT', '30'))
    session = TimeoutSession(timeout_seconds)
    path = os.getenv('YOUTUBE_COOKIES_FILE', '')
    if not path:
        return session
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        print(f'Warning: YOUTUBE_COOKIES_FILE not found at {expanded}, '
              'proceeding without cookies.', flush=True)
        return session
    jar = http.cookiejar.MozillaCookieJar(expanded)
    jar.load(ignore_discard=True, ignore_expires=True)
    session.cookies = jar
    return session


def get_transcript(vid_id: str):
    """Fetch a transcript, falling back to the first available language."""
    api = YouTubeTranscriptApi(http_client=build_http_client())
    try:
        return api.fetch(vid_id)
    except CouldNotRetrieveTranscript:
        transcript_list = api.list(vid_id)
        return next(iter(transcript_list)).fetch()


class YouTubeService:
    """Wraps YouTube Data API v3 for playlist/video metadata."""

    def __init__(self, api_key: str):
        self._svc = build('youtube', 'v3', developerKey=api_key)

    def get_latest_playlist_videos(self, pl_id: str, count: int = 3) -> list[dict]:
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
                    playlistId=pl_id,
                    maxResults=50,
                    pageToken=page_token,
                ).execute(num_retries=3)
            except HttpError as e:
                raise RuntimeError(f'YouTube API error fetching playlist {pl_id}: '
                                   f'{e.status_code} {e.reason}') from e

            items.extend(resp.get('items', []))
            page_token = resp.get('nextPageToken')
            if not page_token:
                break

        if not items:
            raise RuntimeError(f'No videos found in playlist: {pl_id}')

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
            ).execute(num_retries=3)
        except HttpError as e:
            raise RuntimeError(f'YouTube API error fetching durations: '
                               f'{e.status_code} {e.reason}') from e

        return {
            item['id']: parse_duration_seconds(item['contentDetails']['duration'])
            for item in resp.get('items', [])
        }

    def get_video_info(self, vid_id: str) -> dict:
        """Return title, published_at, and duration for a single video."""
        try:
            resp = self._svc.videos().list(
                part='snippet,contentDetails',
                id=vid_id,
            ).execute(num_retries=3)
        except HttpError as e:
            raise RuntimeError(f'YouTube API error fetching video {vid_id}: '
                               f'{e.status_code} {e.reason}') from e

        items = resp.get('items', [])
        if not items:
            raise RuntimeError(f'Video not found: {vid_id}')
        snippet = items[0]['snippet']
        duration = items[0]['contentDetails']['duration']
        return {
            'id': vid_id,
            'title': snippet['title'],
            'published_at': snippet['publishedAt'],
            'duration_seconds': parse_duration_seconds(duration),
        }


@contextlib.contextmanager
def _silent_progress(_message):
    yield


class IngestionService:
    """Fetches podcast transcripts from YouTube and writes them as markdown files."""

    def __init__(self, youtube: YouTubeService | None = None, progress=None):
        self._youtube = youtube or YouTubeService(get_api_key())
        self._progress = progress or _silent_progress

    def fetch_video(self, video_url: str, name: str, out_dir: str,
                    dry_run: bool = False) -> None:
        """Fetch and save the transcript for one explicitly requested video."""
        vid_id = video_id(video_url)

        with self._progress(f'[{name}] Fetching video info...'):
            video = self._youtube.get_video_info(vid_id)

        print(f'[{name}] Title: {video["title"]}', flush=True)
        print(f'[{name}] Video ID: {vid_id}', flush=True)

        # A single explicitly requested video should fail loudly (nonzero exit),
        # unlike batch playlist runs which log and continue.
        self._save_transcript(name, video, out_dir, dry_run=dry_run, catch_errors=False)

    def fetch_playlist(self, name: str, playlist_url: str, count: int, out_dir: str,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                       dry_run: bool = False) -> None:
        """Fetch and save the newest `count` episodes of a single playlist."""
        videos = self._fetch_playlist_videos(name, playlist_url, count)
        for i, video in enumerate(videos):
            self._process_video_entry(name, video, out_dir, add_delay=(i > 0), dry_run=dry_run)

    def fetch_all(self, playlists: list[dict], count: int, out_dir: str,
                  dry_run: bool = False) -> None:
        """Fetch the newest `count` episodes of every playlist, round-robin by recency.

        Episodes are processed newest-first across all playlists (all the #1s, then
        all the #2s, ...) so a failure late in the run costs the oldest items first.
        """
        print(f'Processing {len(playlists)} playlist(s), {count} episode(s) each...', flush=True)

        playlist_videos = []
        for entry in playlists:
            try:
                videos = self._fetch_playlist_videos(entry['name'], entry['url'], count)
                playlist_videos.append((entry['name'], videos))
            except Exception as e:  # pylint: disable=broad-except
                print(f'[{entry["name"]}] Error fetching playlist: {e}', flush=True)

        first_transcript = True
        for i in range(count):
            for name, videos in playlist_videos:
                if i >= len(videos):
                    continue
                try:
                    self._process_video_entry(name, videos[i], out_dir,
                                              add_delay=not first_transcript, dry_run=dry_run)
                    first_transcript = False
                except Exception as e:  # pylint: disable=broad-except
                    print(f'[{name}] Error processing episode {i + 1}: {e}', flush=True)

        print('\nAll done.', flush=True)

    def _fetch_playlist_videos(self, name: str, playlist_url: str, count: int) -> list[dict]:
        with self._progress(f'[{name}] Fetching playlist info...'):
            videos = self._youtube.get_latest_playlist_videos(playlist_id(playlist_url),
                                                              count=count)
        print(f'[{name}] Found {len(videos)} video(s).', flush=True)
        return videos

    def _process_video_entry(self, name: str, video: dict, out_dir: str,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                             add_delay: bool = False, dry_run: bool = False) -> None:
        print(f'[{name}] {video["title"]}', flush=True)
        self._save_transcript(name, video, out_dir, add_delay=add_delay, dry_run=dry_run,
                              indent='  ')

    def _save_transcript(self, name: str, video: dict, out_dir: str,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                         add_delay: bool = False, dry_run: bool = False, indent: str = '',
                         catch_errors: bool = True) -> None:
        filename = os.path.join(out_dir, f'{safe_filename(video["title"])}.md')

        if os.path.exists(filename):
            print(f'[{name}] {indent}Skipped (already exists): {filename}', flush=True)
            return

        if dry_run:
            print(f'[{name}] {indent}Would save: {filename}', flush=True)
            return

        if add_delay:
            time.sleep(3)

        try:
            with self._progress(f'[{name}] {indent}Fetching transcript...'):
                transcript = get_transcript(video['id'])
            body = format_transcript(transcript)
        except Exception as e:  # pylint: disable=broad-except
            if not catch_errors:
                raise
            print(f'[{name}] {indent}Transcript error: {e}', flush=True)
            return

        source_url = f'https://www.youtube.com/watch?v={video["id"]}'
        os.makedirs(out_dir, exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(build_frontmatter(format_date(video['published_at']), source_url,
                                      name, video.get('duration_seconds')))
            f.write('\n')
            f.write(body)
            f.write('\n')

        print(f'[{name}] {indent}Saved to {filename}', flush=True)
