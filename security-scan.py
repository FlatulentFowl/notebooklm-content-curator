"""
Security and privacy scanner for the productivity-agent repository.

Checks for: hardcoded secrets, personal data in tracked files, git history
exposure, missing gitignore entries, and overly permissive file permissions.

Run before any commit touching credential/config handling, and before
making the repository public.

Usage: python3 security-scan.py [--strict]
  --strict  Exit with code 1 if any MEDIUM or higher findings exist.
            Without this flag, only CRITICAL findings cause a non-zero exit.
"""

import argparse
import os
import re
import stat
import subprocess
import sys

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    # OAuth / API credentials
    (re.compile(r'client_secret\s*=\s*["\'][^"\']{8,}["\']', re.I), 'OAuth client_secret literal'),
    (re.compile(r'client_id\s*=\s*["\'][^"\']{8,}["\']', re.I), 'OAuth client_id literal'),
    (re.compile(r'api[_-]?key\s*=\s*["\'][^"\']{8,}["\']', re.I), 'API key literal'),
    (re.compile(r'bearer\s+[A-Za-z0-9\-._~+/]{20,}', re.I), 'Bearer token'),
    # Generic high-entropy-looking assignments
    (re.compile(r'(password|passwd|secret|token)\s*=\s*["\'][^"\']{6,}["\']', re.I), 'Credential assignment'),
    # Google-specific
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}'), 'Google API key (AIza...)'),
    (re.compile(r'"type"\s*:\s*"service_account"'), 'Service account JSON'),
    # GitHub PAT formats
    (re.compile(r'gh[ps]_[A-Za-z0-9]{36}'), 'GitHub PAT (ghp_/ghs_)'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{82}'), 'GitHub fine-grained PAT'),
    # Generic base64-ish long strings assigned to secret-sounding names
    (re.compile(r'(private_key|refresh_token)\s*[=:]\s*["\'][^"\']{20,}["\']', re.I), 'Private key / refresh token literal'),
]

EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_PATTERN = re.compile(r'\b(\+27|0)[0-9]{9}\b')
FULL_NAME_PATTERN = re.compile(r'"[A-Z][a-z]+ [A-Z][a-z]+"')

# Filenames that must never be tracked in git
SENSITIVE_FILENAMES = {
    'credentials.json',
    'settings.json',
    'config.json',
    '.env',
    'ghPAT',
    'ghPAT.pub',
}

# Gitignore patterns that must be present
REQUIRED_GITIGNORE_ENTRIES = [
    'settings.json',
    'config.json',
    'credentials.json',
    '.env',
    '*.token.json',
    'google-*-token.json',
]

# File extensions to scan for secrets/PII
SCAN_EXTENSIONS = {'.py', '.json', '.env', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.txt', '.md'}

# Files/dirs to skip entirely
SKIP_PATHS = {'.git', '.venv', '__pycache__', 'raw', 'test', 'node_modules'}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
findings = []


def finding(severity, location, message, detail=''):
    findings.append({
        'severity': severity,
        'location': location,
        'message': message,
        'detail': detail,
    })


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def project_root():
    return os.path.dirname(os.path.abspath(__file__))


def git_tracked_files():
    out = run(['git', 'ls-files'])
    return set(out.splitlines()) if out else set()


def git_history_files():
    """All file paths that ever appeared in git history."""
    out = run(['git', 'log', '--all', '--name-only', '--pretty=format:'])
    return set(line for line in out.splitlines() if line.strip())


def gitignore_contents():
    path = os.path.join(project_root(), '.gitignore')
    if not os.path.exists(path):
        return ''
    with open(path, encoding='utf-8') as f:
        return f.read()


def walk_source_files():
    root = project_root()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_PATHS and not d.startswith('.')]
        for fname in filenames:
            if fname.startswith('.') and fname not in {'.env', '.env.example', '.gitignore'}:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in SCAN_EXTENSIONS or fname in {'.env', '.env.example'}:
                yield os.path.join(dirpath, fname)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_secrets_in_files():
    root = project_root()
    for filepath in walk_source_files():
        rel = os.path.relpath(filepath, root)
        try:
            with open(filepath, encoding='utf-8', errors='ignore') as f:
                for lineno, line in enumerate(f, 1):
                    # Skip comments and env var reads that don't embed a value
                    stripped = line.strip()
                    if stripped.startswith('#'):
                        continue
                    if re.match(r'os\.getenv\(', stripped) and ',' not in stripped:
                        continue

                    for pattern, label in SECRET_PATTERNS:
                        if pattern.search(line):
                            finding('CRITICAL', f'{rel}:{lineno}',
                                    f'Possible {label}',
                                    stripped[:120])
        except OSError:
            pass


def check_personal_data_in_tracked_files():
    root = project_root()
    tracked = git_tracked_files()
    for filepath in walk_source_files():
        rel = os.path.relpath(filepath, root)
        if rel not in tracked:
            continue
        try:
            with open(filepath, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            emails = EMAIL_PATTERN.findall(content)
            if emails:
                # Filter out placeholder/example addresses
                real = [e for e in emails if not any(x in e for x in ['example.com', 'yourdomain', 'user@', 'test@'])]
                if real:
                    finding('HIGH', rel, 'Email address(es) in tracked file', ', '.join(set(real)))
            names = FULL_NAME_PATTERN.findall(content)
            if names:
                finding('HIGH', rel, 'Quoted full name(s) in tracked file — may be personal data', ', '.join(set(names)))
            phones = PHONE_PATTERN.findall(content)
            if phones:
                finding('HIGH', rel, 'Phone number pattern in tracked file', str(phones))
        except OSError:
            pass


def check_sensitive_files_tracked():
    tracked = git_tracked_files()
    for fname in SENSITIVE_FILENAMES:
        if fname in tracked:
            finding('CRITICAL', fname,
                    f'{fname} is tracked by git — it must be gitignored and untracked',
                    'Run: git rm --cached ' + fname)


def check_sensitive_files_in_history():
    history = git_history_files()
    for fname in SENSITIVE_FILENAMES:
        if fname in history:
            finding('HIGH', fname,
                    f'{fname} appears in git history',
                    'Rewrite history with: git filter-repo --path ' + fname + ' --invert-paths')
    # Generic patterns in history
    token_pat = re.compile(r'(google-.*-token\.json|.*\.token\.json|credentials\.json)$')
    for hfile in history:
        if token_pat.match(os.path.basename(hfile)):
            finding('HIGH', hfile, 'Token/credential file in git history',
                    'Rewrite history with git filter-repo to remove it')


def check_gitignore_coverage():
    content = gitignore_contents()
    if not content:
        finding('HIGH', '.gitignore', '.gitignore is missing entirely')
        return
    for entry in REQUIRED_GITIGNORE_ENTRIES:
        if entry not in content:
            finding('MEDIUM', '.gitignore',
                    f'Required entry missing from .gitignore: {entry}')


def check_file_permissions():
    config_dir = os.path.expanduser(os.getenv('GOOGLE_CONFIG_DIR', '~/.config/productivity-agent'))
    candidates = []
    if os.path.isdir(config_dir):
        for fname in os.listdir(config_dir):
            candidates.append(os.path.join(config_dir, fname))
    # Also check local project credential files
    root = project_root()
    for fname in ['credentials.json', 'settings.json', '.env']:
        path = os.path.join(root, fname)
        if os.path.exists(path):
            candidates.append(path)

    for path in candidates:
        try:
            mode = os.stat(path).st_mode
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                finding('MEDIUM', path,
                        f'Credential/config file is readable by group or others (mode: {oct(mode & 0o777)})',
                        'Run: chmod 600 ' + path)
        except OSError:
            pass


def check_env_fallback_secrets():
    """Warn about os.getenv() calls with non-empty string fallbacks that look secret."""
    root = project_root()
    pattern = re.compile(r'os\.getenv\(["\']([^"\']+)["\'],\s*["\']([^"\']{6,})["\']')
    for filepath in walk_source_files():
        if not filepath.endswith('.py'):
            continue
        rel = os.path.relpath(filepath, root)
        try:
            with open(filepath, encoding='utf-8', errors='ignore') as f:
                for lineno, line in enumerate(f, 1):
                    m = pattern.search(line)
                    if m:
                        var_name, fallback = m.group(1), m.group(2)
                        secret_words = {'key', 'secret', 'token', 'password', 'credential', 'id'}
                        if any(w in var_name.lower() for w in secret_words):
                            finding('MEDIUM', f'{rel}:{lineno}',
                                    f'os.getenv("{var_name}") has a non-empty secret-looking fallback',
                                    line.strip()[:120])
        except OSError:
            pass


def check_direct_file_reads_of_config():
    """Flag any script that reads settings.json / config.json directly instead of via load_config()."""
    root = project_root()
    pattern = re.compile(r'open\([^)]*(?:settings|config)\.json', re.I)
    for filepath in walk_source_files():
        if not filepath.endswith('.py'):
            continue
        rel = os.path.relpath(filepath, root)
        if rel == 'agent_utils.py':
            continue
        try:
            with open(filepath, encoding='utf-8', errors='ignore') as f:
                for lineno, line in enumerate(f, 1):
                    if pattern.search(line):
                        finding('LOW', f'{rel}:{lineno}',
                                'Direct file read of config — use agent_utils.load_config() instead',
                                line.strip()[:120])
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report():
    sorted_findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f['severity'], 99))

    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in sorted_findings:
        counts[f['severity']] = counts.get(f['severity'], 0) + 1

    if not findings:
        print('No findings. Repository looks clean.')
        return 0

    print(f'\n{"=" * 60}')
    print(f'  Security Scan Results')
    print(f'{"=" * 60}')
    print(f'  CRITICAL: {counts["CRITICAL"]}  HIGH: {counts["HIGH"]}  '
          f'MEDIUM: {counts["MEDIUM"]}  LOW: {counts["LOW"]}')
    print(f'{"=" * 60}\n')

    for f in sorted_findings:
        sev = f['severity']
        print(f'[{sev}] {f["location"]}')
        print(f'       {f["message"]}')
        if f['detail']:
            print(f'       > {f["detail"]}')
        print()

    return counts['CRITICAL']


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Security and privacy scanner.')
    parser.add_argument('--strict', action='store_true',
                        help='Exit 1 on any MEDIUM or higher finding (default: exit 1 on CRITICAL only)')
    args = parser.parse_args()

    print('Running security scan...\n')

    check_secrets_in_files()
    check_personal_data_in_tracked_files()
    check_sensitive_files_tracked()
    check_sensitive_files_in_history()
    check_gitignore_coverage()
    check_file_permissions()
    check_env_fallback_secrets()
    check_direct_file_reads_of_config()

    critical_count = print_report()

    sorted_findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f['severity'], 99))
    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in sorted_findings:
        counts[f['severity']] = counts.get(f['severity'], 0) + 1

    if args.strict:
        exit_code = 1 if any(counts[s] > 0 for s in ['CRITICAL', 'HIGH', 'MEDIUM']) else 0
    else:
        exit_code = 1 if critical_count > 0 else 0

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
