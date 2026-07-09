"""Thin CLI for the podcast ingestion service.

All business logic lives in services/ingestion_service.py; this module only
parses arguments and renders progress spinners.
"""

import argparse
import itertools
import sys
import threading
import time

from services.ingestion_service import (
    IngestionService,
    get_fetch_count,
    get_out_dir,
    load_playlists,
)


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


def run(playlist=None, video=None, name='Podcast', out=None, dry_run=False) -> int:
    out = out or get_out_dir()
    service = IngestionService(progress=Spinner)

    if video:
        service.fetch_video(video, name, out, dry_run=dry_run)
        return 0

    if playlist:
        service.fetch_playlist(name, playlist, get_fetch_count(), out, dry_run=dry_run)
        return 0

    playlists = load_playlists()
    if not playlists:
        print('No playlists found in settings.json. Use --playlist to specify one.', flush=True)
        return 0

    service.fetch_all(playlists, get_fetch_count(), out, dry_run=dry_run)
    return 0


def main():
    parser = argparse.ArgumentParser(description='Fetch recent podcast transcripts from YouTube playlists.')
    parser.add_argument('--playlist', help='Single playlist URL or ID to process (overrides settings.json)')
    parser.add_argument('--video', help='Single video URL or ID to fetch transcript for')
    parser.add_argument('--name', default='Podcast', help='Name for the playlist/video when using --playlist or --video')
    parser.add_argument('--out', default=get_out_dir(), help='Output directory (default: ~/scm-coe/raw/transcripts/podcast)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Fetch metadata only; print what would be saved without fetching transcripts or writing files')
    args = parser.parse_args()

    sys.exit(run(playlist=args.playlist, video=args.video, name=args.name,
                 out=args.out, dry_run=args.dry_run))


if __name__ == '__main__':
    main()
