"""
Main entry point for the productivity agent suite.

Usage:
  python3 src/prod_agent.py all [--dry-run]
  python3 src/prod_agent.py meet [--date DATE] [--dry-run]
  python3 src/prod_agent.py tasks [--dry-run]
  python3 src/prod_agent.py notebooklm [--dry-run]
  python3 src/prod_agent.py podcast [--playlist URL] [--video URL] [--name NAME] [--out DIR]
"""

import argparse
import os
import subprocess
import sys

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))


def _run(script, args):
    cmd = [sys.executable, os.path.join(_SRC_DIR, script)] + args
    return subprocess.run(cmd, check=False).returncode


def _meet(args):
    extra = []
    if getattr(args, 'date', None):
        extra += ['--date', args.date]
    if getattr(args, 'dry_run', False):
        extra.append('--dry-run')
    return _run('prod_agent_meet.py', extra)


def _tasks(args):
    extra = ['--dry-run'] if getattr(args, 'dry_run', False) else []
    return _run('prod_agent_tasks.py', extra)


def _notebooklm(args):
    extra = ['--dry-run'] if getattr(args, 'dry_run', False) else []
    return _run('prod_agent_notebooklm.py', extra)


def _podcast(args):
    extra = []
    if getattr(args, 'playlist', None):
        extra += ['--playlist', args.playlist]
    if getattr(args, 'video', None):
        extra += ['--video', args.video]
    name = getattr(args, 'name', None)
    if name and name != 'Podcast':
        extra += ['--name', name]
    if getattr(args, 'out', None):
        extra += ['--out', args.out]
    return _run('prod_agent_podcast.py', extra)


def _all(args):
    dry_run = getattr(args, 'dry_run', False)
    codes = []

    print('=== meet ===')
    codes.append(_meet(args))

    print('\n=== tasks ===')
    codes.append(_tasks(args))

    print('\n=== notebooklm ===')
    codes.append(_notebooklm(args))

    if dry_run:
        print('\n=== podcast === (skipped in dry-run — podcast has no dry-run mode)')
    else:
        print('\n=== podcast ===')
        codes.append(_podcast(args))

    return max(codes) if codes else 0


def main():
    parser = argparse.ArgumentParser(
        prog='prod-agent',
        description='Productivity agent — run one or all agents.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'agents:\n'
            '  all          Run all agents in sequence (meet → tasks → notebooklm → podcast)\n'
            '  meet         Import Google Meet Gemini notes → Google Tasks\n'
            '  tasks        Promote checkbox notes to subtasks\n'
            '  notebooklm   Upload tagged markdown files to Google Drive\n'
            '  podcast      Fetch YouTube playlist transcripts\n'
        ),
    )
    sub = parser.add_subparsers(dest='agent', metavar='agent')
    sub.required = True

    p_all = sub.add_parser('all', help='Run all agents in sequence')
    p_all.add_argument('--dry-run', action='store_true',
                       help='Dry-run meet, tasks, and notebooklm (podcast is skipped in dry-run)')

    p_meet = sub.add_parser('meet', help='Google Meet Gemini notes → Tasks')
    p_meet.add_argument('--date', default=None,
                        help="DD/MM/YYYY, 'today', or omit for previous weekday")
    p_meet.add_argument('--dry-run', action='store_true')

    p_tasks = sub.add_parser('tasks', help='Checkbox notes → subtasks')
    p_tasks.add_argument('--dry-run', action='store_true')

    p_nb = sub.add_parser('notebooklm', help='Tagged markdown files → Google Drive')
    p_nb.add_argument('--dry-run', action='store_true')

    p_pod = sub.add_parser('podcast', help='YouTube playlist → transcript markdown files')
    p_pod.add_argument('--playlist', help='Single playlist URL (overrides settings.json)')
    p_pod.add_argument('--video', help='Single video URL')
    p_pod.add_argument('--name', default='Podcast',
                       help='Name label when using --playlist or --video')
    p_pod.add_argument('--out', help='Output directory (default: ~/scm-coe/raw/transcripts/podcast)')

    args = parser.parse_args()

    dispatch = {
        'all': _all,
        'meet': _meet,
        'tasks': _tasks,
        'notebooklm': _notebooklm,
        'podcast': _podcast,
    }

    sys.exit(dispatch[args.agent](args))


if __name__ == '__main__':
    main()
