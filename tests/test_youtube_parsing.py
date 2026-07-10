"""Unit tests for the pure YouTube parsing/formatting helpers."""

import pytest

from utils.youtube import (
    build_frontmatter,
    format_date,
    format_duration_clock,
    format_label,
    format_transcript,
    parse_duration_seconds,
    playlist_id,
    safe_filename,
    video_id,
    yaml_quote,
)


class TestParseDurationSeconds:
    def test_minutes_seconds(self):
        assert parse_duration_seconds('PT4M13S') == 253

    def test_hours_minutes_seconds(self):
        assert parse_duration_seconds('PT1H2M3S') == 3723

    def test_days_prefix_with_seconds(self):
        # Day component is accepted in the pattern but not counted toward seconds.
        assert parse_duration_seconds('P1DT30S') == 30

    def test_hours_only(self):
        assert parse_duration_seconds('PT2H') == 7200

    def test_garbage_returns_none(self):
        assert parse_duration_seconds('not-a-duration') is None

    def test_empty_returns_none(self):
        assert parse_duration_seconds('') is None


class TestPlaylistId:
    def test_full_url(self):
        assert playlist_id('https://www.youtube.com/playlist?list=PLabc123') == 'PLabc123'

    def test_list_mid_query(self):
        assert playlist_id('https://www.youtube.com/watch?v=x&list=PLxyz&index=2') == 'PLxyz'

    def test_bare_id_passthrough(self):
        assert playlist_id('PLabc123') == 'PLabc123'


class TestVideoId:
    def test_watch_url(self):
        assert video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ') == 'dQw4w9WgXcQ'

    def test_short_url(self):
        assert video_id('https://youtu.be/dQw4w9WgXcQ') == 'dQw4w9WgXcQ'

    def test_watch_url_with_extra_params(self):
        assert video_id('https://www.youtube.com/watch?v=abc123&t=42s') == 'abc123'

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            video_id('https://example.com/nothing-here')


class TestFormatDate:
    def test_iso_with_z_suffix(self):
        assert format_date('2026-07-08T14:30:00Z') == '2026-07-08'

    def test_empty_string(self):
        assert format_date('') == ''

    def test_unparseable_falls_back_to_first_ten_chars(self):
        assert format_date('2026-07-08garbage') == '2026-07-08'


class TestFormatLabel:
    def test_at_shorts_boundary_is_short(self):
        assert format_label(180) == 'Short clip / excerpt'

    def test_above_boundary_is_episode(self):
        assert format_label(181) == 'episode'

    def test_none_is_episode(self):
        assert format_label(None) == 'episode'


class TestFormatDurationClock:
    def test_minutes_seconds(self):
        assert format_duration_clock(253) == '4:13'

    def test_with_hours(self):
        assert format_duration_clock(3723) == '1:02:03'

    def test_none(self):
        assert format_duration_clock(None) == ''


class TestYamlQuote:
    def test_plain(self):
        assert yaml_quote('hello') == '"hello"'

    def test_escapes_quotes_and_backslashes(self):
        assert yaml_quote('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'


class TestBuildFrontmatter:
    def test_golden(self):
        result = build_frontmatter('2026-07-08', 'https://www.youtube.com/watch?v=abc',
                                   'Supply Chain Now', 3723)
        assert result == (
            '---\n'
            'podcastDate: 2026-07-08\n'
            'source: https://www.youtube.com/watch?v=abc\n'
            'podcast: "Supply Chain Now"\n'
            'description: ""\n'
            'format: "episode"\n'
            'duration: "1:02:03"\n'
            '---\n'
        )


class _Snippet:
    def __init__(self, text):
        self.text = text


class TestFormatTranscript:
    def test_joins_and_strips_html(self):
        transcript = [_Snippet('Hello <b>world</b>'), _Snippet('  '), _Snippet('again')]
        assert format_transcript(transcript) == 'Hello world again'

    def test_empty(self):
        assert format_transcript([]) == ''


class TestSafeFilename:
    def test_strips_specials_and_collapses_spaces(self):
        assert safe_filename('Ep. 42: What / Why?  How!') == 'Ep 42 What Why How'

    def test_keeps_hyphens_and_words(self):
        assert safe_filename('supply-chain update 2026') == 'supply-chain update 2026'
