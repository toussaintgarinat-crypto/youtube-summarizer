"""Google Drive Exporter — upload files to Google Drive via OAuth"""

import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Optional

# Lazily imported to avoid forcing the dependency


def check_drive_configured(client_id: Optional[str] = None) -> dict:
    """Check if Google Drive is configured."""
    if not client_id:
        return {"configured": False, "error": "Google Client ID non configuré"}
    return {"configured": True, "error": None}


def get_google_auth_url(client_id: str, redirect_uri: str) -> str:
    """Generate the Google OAuth URL."""
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=https://www.googleapis.com/auth/drive.file&"
        f"access_type=offline&"
        f"prompt=consent"
    )


def exchange_code_for_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchange auth code for tokens."""
    try:
        import requests
    except ImportError:
        return {"success": False, "error": "requests non installé"}

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return {"success": False, "error": f"Erreur token: {resp.text[:200]}"}
    return {"success": True, "tokens": resp.json()}


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh an expired access token."""
    try:
        import requests
    except ImportError:
        return {"success": False, "error": "requests non installé"}

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return {"success": False, "error": f"Erreur refresh: {resp.text[:200]}"}
    return {"success": True, "tokens": resp.json()}


def upload_to_drive(
    file_path: str,
    file_name: str,
    mime_type: str,
    access_token: str,
    folder_name: str = "YouTube Summarizer",
) -> dict:
    """Upload a file to Google Drive."""
    try:
        import requests
    except ImportError:
        return {"success": False, "error": "requests non installé"}

    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Find or create folder
    folder_id = _find_or_create_folder(headers, folder_name)
    if not folder_id:
        return {"success": False, "error": "Impossible de créer le dossier Drive"}

    # 2. Upload file
    metadata = json.dumps({"name": file_name, "parents": [folder_id], "mimeType": mime_type})
    try:
        with open(file_path, "rb") as f:
            files = {
                "metadata": ("metadata", metadata, "application/json"),
                "file": (file_name, f, mime_type),
            }
            resp = requests.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                headers=headers,
                files=files,
                timeout=120,
            )
        if resp.status_code == 200:
            data = resp.json()
            file_id = data.get("id", "")
            return {
                "success": True,
                "file_id": file_id,
                "web_view_link": f"https://drive.google.com/file/d/{file_id}/view",
                "file_name": file_name,
            }
        if resp.status_code == 401:
            return {"success": False, "error": "Token expiré — reconnectez-vous"}
        return {"success": False, "error": f"Drive {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": f"Upload: {str(e)}"}


def _find_or_create_folder(headers: dict, folder_name: str) -> Optional[str]:
    """Find or create a folder in Google Drive."""
    try:
        import requests
    except ImportError:
        return None

    # Search for existing folder
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resp = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        params={"q": query, "fields": "files(id,name)"},
        timeout=15,
    )
    if resp.status_code == 200:
        files = resp.json().get("files", [])
        if files:
            return files[0]["id"]

    # Create folder
    metadata = json.dumps({
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    })
    resp = requests.post(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        data=metadata,
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json().get("id")
    return None


# ── Session state helpers for Streamlit ──────────────────────


def get_drive_status() -> dict:
    """Get placeholder drive status — actual state managed in st.session_state."""
    return {"connected": False}


def get_upload_mime_type(file_type: str) -> str:
    """Get MIME type for a file type."""
    mimes = {
        "txt": "text/plain",
        "md": "text/markdown",
        "pdf": "application/pdf",
        "json": "application/json",
        "excalidraw": "application/json",
        "png": "image/png",
        "jpg": "image/jpeg",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
    }
    return mimes.get(file_type, "application/octet-stream")