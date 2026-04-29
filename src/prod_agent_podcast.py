import argparse
import itertools
import os
import re
import sys
import threading
import time

import yt_dlp
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


def _get_out_dir():
    return os.path.expanduser(os.getenv('PODCAST_OUTPUT_DIR', _FALLBACK_OUT_DIR))


def load_playlists():
    return load_config().get('podcast_playlists', [])


def get_most_recent_video(playlist_url):
    ydl_opts = {'quiet': True, 'extract_flat': True, 'playlistend': 1}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
    entries = info.get('entries', [])
    if not entries:
        raise RuntimeError('No videos found in playlist.')
    return entries[0]


def get_transcript(video_id):
    api = YouTubeTranscriptApi()
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


def process_playlist(playlist_name, playlist_url, out_dir):
    print(f'\n[{playlist_name}] Starting...', flush=True)

    with Spinner(f'[{playlist_name}] Fetching playlist info...'):
        video = get_most_recent_video(playlist_url)

    video_id = video['id']
    title = video.get('title', video_id)
    upload_date = video.get('upload_date', '')

    print(f'[{playlist_name}] Most recent: {title}', flush=True)
    print(f'[{playlist_name}] Video ID:    {video_id}', flush=True)

    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, f'{safe_filename(title)}.md')

    if os.path.exists(filename):
        print(f'[{playlist_name}] Skipped (already exists): {filename}', flush=True)
        return

    with Spinner(f'[{playlist_name}] Fetching transcript...'):
        transcript = get_transcript(video_id)
    body = format_transcript(transcript)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f'# {title}\n\n')
        if upload_date:
            f.write(f'**Date:** {upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}\n\n')
        f.write(f'**Source:** https://www.youtube.com/watch?v={video_id}\n\n')
        f.write('---\n\n')
        f.write(body)
        f.write('\n')

    print(f'[{playlist_name}] Saved to {filename}', flush=True)


def process_video(video_url, name, out_dir):
    video_id = re.search(r'(?:v=|youtu\.be/)([^&?/]+)', video_url)
    if not video_id:
        raise ValueError(f'Could not extract video ID from URL: {video_url}')
    video_id = video_id.group(1)

    with Spinner(f'[{name}] Fetching video info...'):
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    title = info.get('title', video_id)
    upload_date = info.get('upload_date', '')

    print(f'[{name}] Title: {title}', flush=True)
    print(f'[{name}] Video ID: {video_id}', flush=True)

    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, f'{safe_filename(title)}.md')

    if os.path.exists(filename):
        print(f'[{name}] Skipped (already exists): {filename}', flush=True)
        return

    with Spinner(f'[{name}] Fetching transcript...'):
        transcript = get_transcript(video_id)
    body = format_transcript(transcript)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f'# {title}\n\n')
        if upload_date:
            f.write(f'**Date:** {upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}\n\n')
        f.write(f'**Source:** https://www.youtube.com/watch?v={video_id}\n\n')
        f.write('---\n\n')
        f.write(body)
        f.write('\n')

    print(f'[{name}] Saved to {filename}', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Fetch the most recent podcast transcript from YouTube playlists.')
    parser.add_argument('--playlist', help='Single playlist URL to process (overrides settings.json)')
    parser.add_argument('--video', help='Single video URL to fetch transcript for')
    parser.add_argument('--name', default='Podcast', help='Name for the playlist/video when using --playlist or --video')
    parser.add_argument('--out', default=_get_out_dir(), help='Output directory (default: ~/scm-coe/raw/transcripts/podcast)')
    args = parser.parse_args()

    if args.video:
        process_video(args.video, args.name, args.out)
        return

    if args.playlist:
        process_playlist(args.name, args.playlist, args.out)
        return

    playlists = load_playlists()
    if not playlists:
        print('No playlists found in settings.json. Use --playlist to specify one.', flush=True)
        return

    print(f'Processing {len(playlists)} playlist(s)...', flush=True)
    for entry in playlists:
        try:
            process_playlist(entry['name'], entry['url'], args.out)
        except Exception as e:  # pylint: disable=broad-except
            print(f'[{entry["name"]}] Error: {e}', flush=True)

    print('\nAll done.', flush=True)


if __name__ == '__main__':
    main()
