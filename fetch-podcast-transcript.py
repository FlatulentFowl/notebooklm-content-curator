import argparse
import json
import os
import re

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

CONFIG_FILE = 'config.json'
RAW_DIR = os.path.expanduser('~/scm-coe/raw/transcripts/podcast')


def load_playlists():
    if not os.path.exists(CONFIG_FILE):
        return []
    with open(CONFIG_FILE, encoding='utf-8') as f:
        config = json.load(f)
    return config.get('podcast_playlists', [])


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
    except Exception:
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
    print(f'\n[{playlist_name}] Fetching playlist info...')
    video = get_most_recent_video(playlist_url)
    video_id = video['id']
    title = video.get('title', video_id)
    upload_date = video.get('upload_date', '')

    print(f'[{playlist_name}] Most recent: {title}')
    print(f'[{playlist_name}] Video ID:    {video_id}')

    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, f'{safe_filename(title)}.md')

    if os.path.exists(filename):
        print(f'[{playlist_name}] Skipped (already exists): {filename}')
        return

    print(f'[{playlist_name}] Fetching transcript...')
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

    print(f'[{playlist_name}] Saved to {filename}')


def main():
    parser = argparse.ArgumentParser(description='Fetch the most recent podcast transcript from YouTube playlists.')
    parser.add_argument('--playlist', help='Single playlist URL to process (overrides config.json)')
    parser.add_argument('--name', default='Podcast', help='Name for the playlist when using --playlist')
    parser.add_argument('--out', default=RAW_DIR, help='Output directory (default: raw)')
    args = parser.parse_args()

    if args.playlist:
        process_playlist(args.name, args.playlist, args.out)
        return

    playlists = load_playlists()
    if not playlists:
        print('No playlists found in config.json. Use --playlist to specify one.')
        return

    for entry in playlists:
        try:
            process_playlist(entry['name'], entry['url'], args.out)
        except Exception as e:
            print(f'[{entry["name"]}] Error: {e}')


if __name__ == '__main__':
    main()
