#!/usr/bin/env python3
"""
NotebookLM Source Curator
Syncs tagged markdown files to a Google Doc for use as NotebookLM sources.

Usage:
    python notebooklm_sync.py [--dry-run] [--dir PATH]

Setup:
    1. Enable Google Docs API and Drive API in Google Cloud Console
    2. Create OAuth2 credentials (Desktop App type)
    3. Download credentials JSON to: ~/.config/notebooklm-curator/credentials.json
    4. pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pyyaml
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Google API imports ──────────────────────────────────────────────────────
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pyyaml")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml. Install with:  pip install pyyaml")
    sys.exit(1)

# ── Constants ───────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.readonly",
]
REGISTRY_FILENAME = "notebooklm-registry.json"
TOKEN_PATH = Path.home() / ".config" / "notebooklm-curator" / "token.json"
_LEGACY_TOKEN_PATH = Path.home() / ".config" / "notebooklm-curator" / "token.pickle"
CREDENTIALS_PATH = Path.home() / ".config" / "notebooklm-curator" / "credentials.json"
NOTEBOOKLM_TAG = "notebooklm-source"
MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB — Google Docs API batchUpdate limit


# ── Authentication ───────────────────────────────────────────────────────────
def _save_token(creds: Credentials) -> None:
    """Write credentials as JSON with owner-only permissions (0o600)."""
    token_json = creds.to_json()
    # Open with O_CREAT | O_TRUNC so the file is created fresh at 0o600.
    # This prevents a window where a world-readable file exists before chmod.
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token_json)


def get_credentials() -> Credentials:
    """Return valid Google OAuth2 credentials, refreshing or prompting as needed."""
    creds = None
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Migrate away from the old pickle-based token (arbitrary code execution risk).
    if _LEGACY_TOKEN_PATH.exists():
        _LEGACY_TOKEN_PATH.unlink(missing_ok=True)
        print("  Removed legacy token.pickle — please re-authenticate.")

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            print("  Cached token is corrupt — re-authenticating.")
            TOKEN_PATH.unlink(missing_ok=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_token(creds)
            except Exception:
                print("  Token refresh failed (revoked?) — re-authenticating.")
                TOKEN_PATH.unlink(missing_ok=True)
                creds = None

    if not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            print(f"ERROR: credentials file not found at {CREDENTIALS_PATH}")
            print()
            print("One-time setup (uses your existing Google account):")
            print("  1. Go to https://console.cloud.google.com")
            print("  2. Create a project (any name)")
            print("  3. Enable: Google Docs API + Google Drive API")
            print("  4. Go to APIs & Services → Credentials → Create Credentials → OAuth client ID")
            print("  5. Choose 'Desktop app', download the JSON")
            print(f"  6. Save it to: {CREDENTIALS_PATH}")
            print()
            print("After that, running this script will open a browser to sign in.")
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        _save_token(creds)

    return creds


# ── Registry helpers ─────────────────────────────────────────────────────────
def load_registry(cwd: Path) -> dict:
    registry_path = cwd / REGISTRY_FILENAME
    if registry_path.exists():
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Registry file is corrupt ({e}). Starting fresh.")
    return {
        "google_doc_name": "frictionless-supply-chain-notebooklm",
        "google_doc_id": None,
        "last_sync": None,
        "tabs": {},
    }


def save_registry(cwd: Path, registry: dict) -> None:
    registry_path = cwd / REGISTRY_FILENAME
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    print(f"Registry saved → {registry_path}")


# ── File scanning ─────────────────────────────────────────────────────────────
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(content: str) -> dict:
    """Return parsed YAML frontmatter, or {} if absent / unparseable."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter block from content, returning only the markdown body."""
    return _FRONTMATTER_RE.sub("", content, count=1).lstrip("\n")


def has_notebooklm_tag(frontmatter: dict) -> bool:
    """
    Return True when the frontmatter marks the file as a NotebookLM source.

    Accepted forms:
        tags: [notebooklm-source, ...]       # list
        tags:
          - notebooklm-source                # block list
        notebooklm-source: true              # standalone boolean key
    """
    tags = frontmatter.get("tags")
    if tags is not None:
        if isinstance(tags, list):
            return NOTEBOOKLM_TAG in [str(t) for t in tags]
        if isinstance(tags, str):
            return tags == NOTEBOOKLM_TAG
    # Also accept a bare `notebooklm-source: true` key
    return bool(frontmatter.get(NOTEBOOKLM_TAG))


def derive_title(file_path: Path, content: str) -> str:
    """Return the H1 heading, or a title-cased version of the filename."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return file_path.stem.replace("-", " ").replace("_", " ").title()


def file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def scan_tagged_files(cwd: Path) -> list[dict]:
    """Return metadata for all .md files whose YAML frontmatter includes the notebooklm-source tag."""
    results = []
    for md_path in sorted(cwd.rglob("*.md")):
        # Skip symlinks — they could point to sensitive files outside the directory.
        if md_path.is_symlink():
            continue
        try:
            stat = md_path.stat()
        except OSError:
            continue
        if stat.st_size > MAX_FILE_BYTES:
            print(f"  WARNING: '{md_path.name}' exceeds {MAX_FILE_BYTES // 1024}KB — skipping.")
            continue
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        frontmatter = parse_frontmatter(content)
        if not has_notebooklm_tag(frontmatter):
            continue
        results.append(
            {
                "file": md_path.name,
                "file_path": str(md_path),
                "tab_title": derive_title(md_path, content),
                "last_modified": mtime.isoformat(),
                "hash": file_hash(content),
                "content": strip_frontmatter(content),
            }
        )
    return results


def disambiguate_titles(files: list[dict]) -> list[dict]:
    """Append filename to duplicate tab titles."""
    counts: dict[str, int] = {}
    for f in files:
        counts[f["tab_title"]] = counts.get(f["tab_title"], 0) + 1
    result = []
    for f in files:
        f = dict(f)
        if counts[f["tab_title"]] > 1:
            f["tab_title"] = f"{f['tab_title']} ({f['file']})"
        result.append(f)
    return result


# ── Google Docs helpers ───────────────────────────────────────────────────────
def find_or_get_doc(
    docs_svc, drive_svc, registry: dict
) -> tuple[Optional[str], Optional[dict]]:
    """
    Return (doc_id, full_document) for the target Google Doc.
    Caches the doc_id in the registry after first lookup.
    """
    doc_id = registry.get("google_doc_id")

    if not doc_id:
        name = registry.get("google_doc_name", "frictionless-supply-chain-notebooklm")
        print(f'Searching Google Drive for: "{name}"')
        resp = (
            drive_svc.files()
            .list(
                q=(
                    "name='" + name.replace("'", "\\'") + "' and "
                    "mimeType='application/vnd.google-apps.document' and "
                    "trashed=false"
                ),
                spaces="drive",
                fields="files(id, name)",
            )
            .execute()
        )
        files = resp.get("files", [])
        if not files:
            return None, None
        if len(files) > 1:
            print(
                f"WARNING: {len(files)} docs share this name. "
                f"Using the first: {files[0]['id']}"
            )
        doc_id = files[0]["id"]
        registry["google_doc_id"] = doc_id
        print(f"Found: {files[0]['name']}  (ID: {doc_id})")

    document = (
        docs_svc.documents()
        .get(documentId=doc_id, includeTabsContent=True)
        .execute()
    )
    return doc_id, document


def extract_tabs(document: dict) -> list[dict]:
    """Parse tab metadata + emptiness from a full document response."""
    tabs = []
    for raw in document.get("tabs", []):
        props = raw.get("tabProperties", {})
        body_content = (
            raw.get("documentTab", {}).get("body", {}).get("content", [])
        )

        # A tab is "empty" when its body holds nothing but a lone newline paragraph
        non_empty = False
        for element in body_content:
            for pe in element.get("paragraph", {}).get("elements", []):
                text = pe.get("textRun", {}).get("content", "")
                if text.strip():
                    non_empty = True
                    break

        tabs.append(
            {
                "tab_id": props.get("tabId", ""),
                "title": props.get("title", ""),
                "index": props.get("index", 0),
                "is_empty": not non_empty,
                "body_content": body_content,
            }
        )
    return sorted(tabs, key=lambda t: t["index"])


def body_end_index(body_content: list) -> int:
    """Return the highest endIndex found in a tab's body content."""
    end = 1
    for element in body_content:
        if "endIndex" in element:
            end = max(end, element["endIndex"])
        for pe in element.get("paragraph", {}).get("elements", []):
            if "endIndex" in pe:
                end = max(end, pe["endIndex"])
    return end


def clear_tab(docs_svc, doc_id: str, tab_id: str, body_content: list) -> None:
    """Delete all content in a tab (leaves the mandatory trailing newline)."""
    end = body_end_index(body_content)
    if end <= 2:
        return  # Nothing to clear
    docs_svc.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "deleteContentRange": {
                        "range": {
                            "tabId": tab_id,
                            "startIndex": 1,
                            "endIndex": end - 1,
                        }
                    }
                }
            ]
        },
    ).execute()


def insert_into_tab(docs_svc, doc_id: str, tab_id: str, content: str) -> None:
    """Insert text at the beginning of a (freshly cleared) tab."""
    docs_svc.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": tab_id},
                        "text": content,
                    }
                }
            ]
        },
    ).execute()


def rename_tab(docs_svc, doc_id: str, tab_id: str, new_title: str) -> None:
    """Rename a tab. Silently skips if the API does not support it."""
    try:
        docs_svc.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "updateDocumentTab": {
                            "tabId": tab_id,
                            "documentTab": {
                                "tabProperties": {
                                    "title": new_title,
                                }
                            },
                            "fields": "tabProperties.title",
                        }
                    }
                ]
            },
        ).execute()
    except HttpError:
        print(f"    (Tab rename not supported by API — tab title left as-is)")


def fetch_fresh_doc(docs_svc, doc_id: str) -> dict:
    return (
        docs_svc.documents()
        .get(documentId=doc_id, includeTabsContent=True)
        .execute()
    )


# ── Integrity check ───────────────────────────────────────────────────────────
def integrity_check(registry: dict, doc_tabs: list[dict]) -> list[str]:
    """Warn about registry entries whose tab can no longer be found in the doc."""
    warnings = []
    doc_by_id = {t["tab_id"]: t for t in doc_tabs}
    doc_by_title = {t["title"]: t for t in doc_tabs}

    for tab_key, entry in registry.get("tabs", {}).items():
        tab_id = entry.get("tab_id")
        tab_title = entry.get("tab_title", "")

        found_by_id = tab_id and tab_id in doc_by_id
        found_by_title = tab_title in doc_by_title

        if not found_by_id and not found_by_title:
            warnings.append(
                f"Registry entry '{tab_key}' → '{tab_title}' not found in the Google Doc "
                f"(tab may have been renamed or deleted)."
            )
        elif found_by_title and not found_by_id:
            # Tab was found by title but ID changed — update the stored ID
            entry["tab_id"] = doc_by_title[tab_title]["tab_id"]

    return warnings


# ── Classification ────────────────────────────────────────────────────────────
def classify(
    tagged_files: list[dict], registry: dict
) -> dict:
    """
    Returns:
        {
            "add":      [...],        # new files
            "update":   [...],        # modified files
            "skip":     [...],        # unchanged files
            "warnings": [str, ...],   # tag-removed / missing-file messages
        }
    """
    tagged_by_path = {f["file_path"]: f for f in tagged_files}
    registry_by_path = {
        entry["file_path"]: (key, entry)
        for key, entry in registry.get("tabs", {}).items()
    }

    actions: dict = {"add": [], "update": [], "skip": [], "warnings": []}

    for f in tagged_files:
        path = f["file_path"]
        if path not in registry_by_path:
            actions["add"].append(f)
        else:
            key, entry = registry_by_path[path]
            if f["hash"] == entry.get("hash", ""):
                actions["skip"].append({**f, "_tab_key": key, "_entry": entry})
            else:
                actions["update"].append({**f, "_tab_key": key, "_entry": entry})

    # Detect registry entries that are gone or de-tagged
    for key, entry in registry.get("tabs", {}).items():
        path = entry.get("file_path", "")
        if path in tagged_by_path:
            continue  # still active
        if os.path.exists(path):
            actions["warnings"].append(
                f"'{entry['file']}' — {NOTEBOOKLM_TAG!r} tag removed. "
                f"Tab '{entry.get('tab_title', key)}' left intact.\n"
                f"    → Please confirm: should this tab be cleared or kept?"
            )
        else:
            actions["warnings"].append(
                f"'{entry['file']}' — file no longer found on disk. "
                f"Tab '{entry.get('tab_title', key)}' left intact."
            )

    return actions


# ── Report ────────────────────────────────────────────────────────────────────
def print_report(
    actions: dict,
    doc_tabs: list[dict],
    integrity_warnings: list[str],
    dry_run: bool,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    label = "DRY RUN Preview" if dry_run else "Sync Report"

    total_tabs = len(doc_tabs)
    empty_count = sum(1 for t in doc_tabs if t["is_empty"])
    used_count = total_tabs - empty_count

    added   = len(actions["add"])
    updated = len(actions["update"])
    skipped = len(actions["skip"])

    print()
    print("=" * 62)
    print(f"📋 NotebookLM {label} — {now}")
    print("=" * 62)

    if dry_run:
        if added:
            print(f"\n➕ Would ADD ({added}):")
            for f in actions["add"]:
                print(f'   • {f["file"]}  →  "{f["tab_title"]}"')
        if updated:
            print(f"\n🔄 Would UPDATE ({updated}):")
            for f in actions["update"]:
                print(f'   • {f["file"]}  →  "{f["tab_title"]}"')
        if skipped:
            print(f"\n⏭️  Would SKIP ({skipped}) — already up to date:")
            for f in actions["skip"]:
                print(f'   • {f["file"]}')
        if not (added or updated or skipped):
            print("\n  No tagged files found.")
    else:
        print(f"\n✅ Added:    {added} file(s)")
        print(f"🔄 Updated:  {updated} file(s)")
        print(f"⏭️  Skipped:  {skipped} file(s) (already up to date)")
        if not (added or updated or skipped):
            print("\nEverything is up to date. No changes needed.")

    all_warnings = integrity_warnings + actions.get("warnings", [])
    if all_warnings:
        print(f"\n⚠️  Warnings:")
        for w in all_warnings:
            print(f"  - {w}")

    print(
        f"\n📊 Tab usage: {used_count} of {total_tabs} tabs used. "
        f"{empty_count} empty tabs remaining."
    )
    print("=" * 62)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync tagged markdown files to a Google Doc for NotebookLM."
    )
    parser.add_argument(
        "--dry-run", "--preview", action="store_true", dest="dry_run",
        help="Show what would change without touching the Google Doc or registry.",
    )
    parser.add_argument(
        "--dir", default="test", metavar="PATH",
        help="Directory to scan (default: test).",
    )
    args = parser.parse_args()

    cwd = Path(args.dir).resolve()
    print(f"Working directory: {cwd}")

    # ── Step 1: Registry ─────────────────────────────────────────────────────
    print("\n[1/8] Loading registry…")
    registry = load_registry(cwd)

    # ── Step 2: Scan files ───────────────────────────────────────────────────
    print("[2/8] Scanning for tagged markdown files…")
    tagged_files = scan_tagged_files(cwd)

    if not tagged_files:
        print(
            f"\n⚠️  No files tagged with '{NOTEBOOKLM_TAG}' found in {cwd}. "
            "Nothing to sync."
        )
        return

    tagged_files = disambiguate_titles(tagged_files)
    print(f"  Found {len(tagged_files)} tagged file(s).")

    # ── Connect to Google ────────────────────────────────────────────────────
    print("\n[Auth] Authenticating with Google…")
    creds = get_credentials()
    docs_svc  = build("docs",  "v1", credentials=creds, cache_discovery=False)
    drive_svc = build("drive", "v3", credentials=creds, cache_discovery=False)

    # ── Step 3: Integrity check ──────────────────────────────────────────────
    print("[3/8] Fetching Google Doc and running integrity check…")
    try:
        doc_id, document = find_or_get_doc(docs_svc, drive_svc, registry)
    except HttpError as e:
        print(f"\nERROR accessing Google: {e}")
        sys.exit(1)

    if not doc_id or document is None:
        doc_name = registry.get("google_doc_name", "frictionless-supply-chain-notebooklm")
        print(f"\n❌ Could not find Google Doc named '{doc_name}'.")
        print(
            "Check the document name or manually add 'google_doc_id' "
            "to notebooklm-registry.json."
        )
        sys.exit(1)

    doc_tabs = extract_tabs(document)
    print(f"  Document has {len(doc_tabs)} tab(s).")

    integrity_warnings = integrity_check(registry, doc_tabs)
    if integrity_warnings:
        print(f"  {len(integrity_warnings)} integrity warning(s) found.")

    # ── Step 4: Classify ─────────────────────────────────────────────────────
    print("[4/8] Classifying files…")
    actions = classify(tagged_files, registry)
    print(
        f"  ADD: {len(actions['add'])}  |  "
        f"UPDATE: {len(actions['update'])}  |  "
        f"SKIP: {len(actions['skip'])}"
    )

    # ── Step 5: Dry-run ──────────────────────────────────────────────────────
    if args.dry_run:
        print_report(actions, doc_tabs, integrity_warnings, dry_run=True)
        return

    # ── Step 6: Sync ─────────────────────────────────────────────────────────
    print("[6/8] Syncing to Google Doc…")

    empty_tabs = [t for t in doc_tabs if t["is_empty"]]
    files_to_add = actions["add"]

    if len(files_to_add) > len(empty_tabs):
        print(
            f"\n❌ Cannot proceed: {len(files_to_add)} files to ADD but only "
            f"{len(empty_tabs)} empty tabs available.\n"
            "Please add more tabs to the Google Doc before running again."
        )
        sys.exit(1)

    now_utc = datetime.now(timezone.utc).isoformat()
    empty_queue = list(empty_tabs)  # consume in order

    # ADD new files
    for file_info in files_to_add:
        tab = empty_queue.pop(0)
        title = file_info["tab_title"]
        print(f"  ➕ ADD  '{file_info['file']}'  →  tab '{tab['title']}' (→ '{title}')")

        try:
            rename_tab(docs_svc, doc_id, tab["tab_id"], title)
            # Clear in case the "empty" tab had invisible whitespace
            fresh = fetch_fresh_doc(docs_svc, doc_id)
            fresh_tabs = {t["tab_id"]: t for t in extract_tabs(fresh)}
            if tab["tab_id"] in fresh_tabs:
                clear_tab(docs_svc, doc_id, tab["tab_id"],
                          fresh_tabs[tab["tab_id"]]["body_content"])
            insert_into_tab(docs_svc, doc_id, tab["tab_id"], file_info["content"])
        except HttpError as e:
            print(f"    ERROR: {e}")
            continue

        tab_key = f"Tab {tab['index'] + 1}"
        registry["tabs"][tab_key] = {
            "file":          file_info["file"],
            "file_path":     file_info["file_path"],
            "tab_title":     title,
            "tab_id":        tab["tab_id"],
            "last_synced":   now_utc,
            "last_modified": file_info["last_modified"],
            "hash":          file_info["hash"],
        }

    # UPDATE changed files
    for file_info in actions["update"]:
        entry     = file_info["_entry"]
        tab_key   = file_info["_tab_key"]
        tab_id    = entry.get("tab_id")
        tab_title = entry.get("tab_title", "")
        new_title = file_info["tab_title"]

        # Resolve tab_id if missing
        if not tab_id:
            match = next((t for t in doc_tabs if t["title"] == tab_title), None)
            if match:
                tab_id = match["tab_id"]
            else:
                print(
                    f"  ⚠️  Cannot locate tab for '{file_info['file']}' "
                    f"(expected '{tab_title}'). Skipping."
                )
                continue

        print(f"  🔄 UPDATE '{file_info['file']}'  in tab '{tab_title}'")

        try:
            fresh = fetch_fresh_doc(docs_svc, doc_id)
            fresh_tabs = {t["tab_id"]: t for t in extract_tabs(fresh)}
            if tab_id not in fresh_tabs:
                print(f"    ERROR: tab_id {tab_id} no longer exists. Skipping.")
                continue
            clear_tab(docs_svc, doc_id, tab_id, fresh_tabs[tab_id]["body_content"])
            insert_into_tab(docs_svc, doc_id, tab_id, file_info["content"])
            if new_title != tab_title:
                rename_tab(docs_svc, doc_id, tab_id, new_title)
        except HttpError as e:
            print(f"    ERROR: {e}")
            continue

        registry["tabs"][tab_key].update(
            {
                "tab_title":     new_title,
                "tab_id":        tab_id,
                "last_synced":   now_utc,
                "last_modified": file_info["last_modified"],
                "hash":          file_info["hash"],
            }
        )

    # ── Step 7: Save registry ────────────────────────────────────────────────
    print("[7/8] Saving registry…")
    registry["last_sync"] = now_utc
    save_registry(cwd, registry)

    # ── Step 8: Report ───────────────────────────────────────────────────────
    print("[8/8] Producing report…")
    try:
        final_doc  = fetch_fresh_doc(docs_svc, doc_id)
        final_tabs = extract_tabs(final_doc)
    except HttpError:
        final_tabs = doc_tabs  # fall back to the tabs we fetched earlier
    print_report(actions, final_tabs, integrity_warnings, dry_run=False)


if __name__ == "__main__":
    main()
