import os

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from agent_utils import get_credentials

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]

# Configuration
DRIVE_FOLDER_ID = '1am1fRfB5DxnMTCB3sBXN9q4dzxKuLERB'
TAG = 'notebooklm-source'
SOURCE_DIRS = [
    os.path.expanduser('~/Library/Mobile Documents/iCloud~md~obsidian/Documents'),
    os.path.expanduser('~/scm-coe')
]

def file_has_tag(file_path, tag):
    """Checks if a file contains the specific tag."""
    try:
        # Only look for .md files
        ext = os.path.splitext(file_path)[1].lower()
        if ext != '.md':
            return False
            
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Search first 100KB for the tag
            content = f.read(100000) 
            # Match tag with or without leading #
            return tag in content or f"#{tag}" in content
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False

def upload_to_drive(service, local_path, folder_id):
    """Uploads or updates a file on Google Drive, converting it to a Google Doc."""
    base_name = os.path.basename(local_path)
    # Strip .md extension for the Google Doc title
    doc_title = os.path.splitext(base_name)[0]
    
    print(f"Found matching file: {doc_title}")
    
    # Search for existing Google Doc with same title in target folder
    safe_title = doc_title.replace("'", "\\'")
    query = f"name = '{safe_title}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])

    file_metadata = {
        'name': doc_title,
        'mimeType': 'application/vnd.google-apps.document',
        'parents': [folder_id]
    }
    
    # Use text/plain as the source mimeType - Drive converter is more stable with it
    media = MediaFileUpload(local_path, mimetype='text/plain', resumable=True)

    if files:
        # Skip if Google Doc already exists
        print(f"Skipped: {doc_title} (already exists)")
    else:
        # Create new Google Doc
        try:
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"Created Google Doc: {doc_title}")
        except Exception as e:
            print(f"Error uploading {doc_title}: {e}")

def main():
    creds = get_credentials('google-notebooklm-token.json', SCOPES)
    service = build('drive', 'v3', credentials=creds)

    found_any = False
    for source_dir in SOURCE_DIRS:
        if not os.path.exists(source_dir):
            print(f"Source directory not found: {source_dir}")
            continue
            
        print(f"Scanning: {source_dir}")
        for root, dirs, files in os.walk(source_dir):
            # Skip hidden directories and .trash
            dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() != '.trash']
            
            for file in files:
                if file.startswith('.'):
                    continue
                
                # Ignore GEMINI.md and README files
                upper_name = file.upper()
                if upper_name == 'GEMINI.MD' or 'README' in upper_name:
                    continue
                    
                file_path = os.path.join(root, file)
                if file_has_tag(file_path, TAG):
                    found_any = True
                    upload_to_drive(service, file_path, DRIVE_FOLDER_ID)
    
    if not found_any:
        print(f"No files found with tag '{TAG}' in the specified directories.")

if __name__ == '__main__':
    main()
