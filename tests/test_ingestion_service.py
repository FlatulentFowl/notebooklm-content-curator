"""Tests for services.ingestion_service with mocked API clients — no network."""

from unittest.mock import MagicMock, patch

import pytest

from services.ingestion_service import (
    IngestionService,
    TimeoutSession,
    YouTubeService,
    build_http_client,
)


def _playlist_item(vid, title, published_at):
    return {
        'snippet': {
            'title': title,
            'publishedAt': published_at,
            'resourceId': {'videoId': vid},
        },
        'contentDetails': {'videoPublishedAt': published_at},
    }


def _fake_youtube_api(pages, durations_items):
    """Build a MagicMock googleapiclient with paginated playlistItems and videos.list."""
    svc = MagicMock()
    playlist_execute = MagicMock(side_effect=pages)
    svc.playlistItems.return_value.list.return_value.execute = playlist_execute
    svc.videos.return_value.list.return_value.execute = MagicMock(
        return_value={'items': durations_items})
    return svc, playlist_execute


class TestYouTubeService:
    def test_pagination_and_newest_first_sort(self):
        pages = [
            {'items': [_playlist_item('old', 'Old', '2026-01-01T00:00:00Z'),
                       _playlist_item('newest', 'Newest', '2026-07-01T00:00:00Z')],
             'nextPageToken': 'p2'},
            {'items': [_playlist_item('mid', 'Mid', '2026-04-01T00:00:00Z')]},
        ]
        durations = [
            {'id': 'newest', 'contentDetails': {'duration': 'PT10M'}},
            {'id': 'mid', 'contentDetails': {'duration': 'PT20M'}},
        ]
        fake_svc, playlist_execute = _fake_youtube_api(pages, durations)

        with patch('services.ingestion_service.build', return_value=fake_svc):
            yt = YouTubeService('fake-key')
        videos = yt.get_latest_playlist_videos('PLx', count=2)

        assert playlist_execute.call_count == 2  # both pages fetched
        assert [v['id'] for v in videos] == ['newest', 'mid']
        assert videos[0]['duration_seconds'] == 600

    def test_api_calls_use_retries(self):
        pages = [{'items': [_playlist_item('a', 'A', '2026-01-01T00:00:00Z')]}]
        fake_svc, playlist_execute = _fake_youtube_api(pages, [])

        with patch('services.ingestion_service.build', return_value=fake_svc):
            yt = YouTubeService('fake-key')
        yt.get_latest_playlist_videos('PLx', count=1)

        playlist_execute.assert_called_with(num_retries=3)
        fake_svc.videos.return_value.list.return_value.execute.assert_called_with(num_retries=3)

    def test_empty_playlist_raises(self):
        fake_svc, _ = _fake_youtube_api([{'items': []}], [])
        with patch('services.ingestion_service.build', return_value=fake_svc):
            yt = YouTubeService('fake-key')
        with pytest.raises(RuntimeError, match='No videos found'):
            yt.get_latest_playlist_videos('PLx')

    def test_get_video_info(self):
        fake_svc = MagicMock()
        fake_svc.videos.return_value.list.return_value.execute.return_value = {
            'items': [{'snippet': {'title': 'T', 'publishedAt': '2026-07-01T00:00:00Z'},
                       'contentDetails': {'duration': 'PT4M13S'}}]
        }
        with patch('services.ingestion_service.build', return_value=fake_svc):
            yt = YouTubeService('fake-key')
        info = yt.get_video_info('abc')
        assert info == {'id': 'abc', 'title': 'T',
                        'published_at': '2026-07-01T00:00:00Z', 'duration_seconds': 253}


def _fake_adapter(videos_by_playlist=None, video_info=None):
    yt = MagicMock(spec=YouTubeService)
    if videos_by_playlist is not None:
        yt.get_latest_playlist_videos.side_effect = (
            lambda pl_id, count=3: videos_by_playlist[pl_id][:count])
    if video_info is not None:
        yt.get_video_info.return_value = video_info
    return yt


_VIDEO = {'id': 'abc', 'title': 'Great Episode', 'published_at': '2026-07-01T00:00:00Z',
          'duration_seconds': 600}


class TestIngestionService:
    def test_dry_run_writes_nothing_and_skips_transcripts(self, tmp_path):
        out = tmp_path / 'out'
        service = IngestionService(youtube=_fake_adapter(video_info=_VIDEO))
        with patch('services.ingestion_service.get_transcript') as transcript:
            service.fetch_video('https://youtu.be/abc', 'Show', str(out), dry_run=True)
        transcript.assert_not_called()
        assert not out.exists()

    def test_fetch_video_writes_frontmatter_and_body(self, tmp_path):
        service = IngestionService(youtube=_fake_adapter(video_info=_VIDEO))
        snippet = MagicMock(text='hello world')
        with patch('services.ingestion_service.get_transcript', return_value=[snippet]):
            service.fetch_video('https://youtu.be/abc', 'Show', str(tmp_path))
        content = (tmp_path / 'Great Episode.md').read_text(encoding='utf-8')
        assert content.startswith('---\npodcastDate: 2026-07-01\n')
        assert 'podcast: "Show"' in content
        assert content.rstrip().endswith('hello world')

    def test_existing_file_skipped_without_transcript_fetch(self, tmp_path):
        (tmp_path / 'Great Episode.md').write_text('already here', encoding='utf-8')
        service = IngestionService(youtube=_fake_adapter(video_info=_VIDEO))
        with patch('services.ingestion_service.get_transcript') as transcript:
            service.fetch_video('https://youtu.be/abc', 'Show', str(tmp_path))
        transcript.assert_not_called()
        assert (tmp_path / 'Great Episode.md').read_text(encoding='utf-8') == 'already here'

    def test_fetch_video_error_propagates(self, tmp_path):
        service = IngestionService(youtube=_fake_adapter(video_info=_VIDEO))
        with patch('services.ingestion_service.get_transcript', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError, match='boom'):
                service.fetch_video('https://youtu.be/abc', 'Show', str(tmp_path))

    def test_fetch_all_continues_after_playlist_error(self, tmp_path, capsys):
        good = [{'id': 'g1', 'title': 'Good One', 'published_at': '2026-07-01T00:00:00Z',
                 'duration_seconds': 600}]
        yt = MagicMock(spec=YouTubeService)
        yt.get_latest_playlist_videos.side_effect = [RuntimeError('quota'), good]
        service = IngestionService(youtube=yt)
        playlists = [{'name': 'Broken', 'url': 'PLbad'}, {'name': 'Works', 'url': 'PLgood'}]

        snippet = MagicMock(text='body')
        with patch('services.ingestion_service.get_transcript', return_value=[snippet]):
            with patch('services.ingestion_service.time.sleep'):
                service.fetch_all(playlists, count=1, out_dir=str(tmp_path))

        captured = capsys.readouterr().out
        assert '[Broken] Error fetching playlist: quota' in captured
        assert (tmp_path / 'Good One.md').exists()


class TestHttpClient:
    def test_default_timeout_applied(self):
        session = TimeoutSession(30)
        with patch('requests.Session.request', return_value=MagicMock()) as req:
            session.request('GET', 'https://example.com')
        assert req.call_args.kwargs['timeout'] == 30

    def test_explicit_timeout_not_overridden(self):
        session = TimeoutSession(30)
        with patch('requests.Session.request', return_value=MagicMock()) as req:
            session.request('GET', 'https://example.com', timeout=5)
        assert req.call_args.kwargs['timeout'] == 5

    def test_cookieless_client_is_still_timeout_session(self, monkeypatch):
        monkeypatch.delenv('YOUTUBE_COOKIES_FILE', raising=False)
        assert isinstance(build_http_client(), TimeoutSession)

    def test_timeout_env_override(self, monkeypatch):
        monkeypatch.delenv('YOUTUBE_COOKIES_FILE', raising=False)
        monkeypatch.setenv('PODCAST_HTTP_TIMEOUT', '7')
        with patch('requests.Session.request', return_value=MagicMock()) as req:
            build_http_client().request('GET', 'https://example.com')
        assert req.call_args.kwargs['timeout'] == 7.0
