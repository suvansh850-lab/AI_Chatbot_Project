"""Core API client for interacting with GitHub REST API."""

import base64
import requests
from typing import Any, Dict, List, Optional


GITHUB_API_URL = "https://api.github.com"


def get_headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Morepen-AI-Assistant/1.0"
    }


def get_github_user(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetches user details for the authenticated user."""
    url = f"{GITHUB_API_URL}/user"
    try:
        response = requests.get(url, headers=get_headers(access_token), timeout=10)
        if response.status_code == 200:
            return response.json()
        print(f"GitHub get_user error (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"GitHub get_user exception: {e}")
    return None


def list_repositories(access_token: str) -> List[Dict[str, Any]]:
    """Lists repositories the user has access to, sorted by last updated."""
    url = f"{GITHUB_API_URL}/user/repos"
    params = {
        "per_page": 100,
        "sort": "updated",
        "type": "all"
    }
    try:
        response = requests.get(
            url, 
            headers=get_headers(access_token), 
            params=params, 
            timeout=15
        )
        if response.status_code == 200:
            return response.json()
        print(f"GitHub list_repos error (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"GitHub list_repos exception: {e}")
    return []


def list_repo_contents(repo_fullname: str, path: str, access_token: str) -> List[Dict[str, Any]]:
    """Lists contents of a directory in the specified repository."""
    # Clean path (no leading slash)
    clean_path = path.strip("/")
    url = f"{GITHUB_API_URL}/repos/{repo_fullname}/contents/{clean_path}"
    try:
        response = requests.get(url, headers=get_headers(access_token), timeout=10)
        if response.status_code == 200:
            res = response.json()
            if isinstance(res, list):
                return res
            # If path points to a file, API returns a dictionary, wrap in a list
            return [res]
        print(f"GitHub list_contents error (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"GitHub list_contents exception: {e}")
    return []


def get_repo_file_content(repo_fullname: str, path: str, access_token: str) -> Optional[str]:
    """Downloads and decodes file content from a repository."""
    clean_path = path.strip("/")
    url = f"{GITHUB_API_URL}/repos/{repo_fullname}/contents/{clean_path}"
    try:
        response = requests.get(url, headers=get_headers(access_token), timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("encoding") == "base64" and data.get("content"):
                # Decode base64 content
                raw_bytes = base64.b64decode(data["content"].encode("utf-8"))
                return raw_bytes.decode("utf-8", errors="ignore")
            # Fallback if content is returned directly or different encoding
            return data.get("content")
        print(f"GitHub get_file_content error (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"GitHub get_file_content exception: {e}")
    return None


def create_github_issue(repo_fullname: str, title: str, body: str, access_token: str) -> Optional[Dict[str, Any]]:
    """Creates a new issue in the specified repository."""
    url = f"{GITHUB_API_URL}/repos/{repo_fullname}/issues"
    payload = {
        "title": title,
        "body": body
    }
    try:
        response = requests.post(
            url, 
            headers=get_headers(access_token), 
            json=payload, 
            timeout=10
        )
        if response.status_code == 201:
            return response.json()
        print(f"GitHub create_issue error (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"GitHub create_issue exception: {e}")
    return None


def create_github_pull_request(
    repo_fullname: str, 
    head: str, 
    base: str, 
    title: str, 
    body: str, 
    access_token: str
) -> Optional[Dict[str, Any]]:
    """Creates a new pull request in the specified repository."""
    url = f"{GITHUB_API_URL}/repos/{repo_fullname}/pulls"
    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base
    }
    try:
        response = requests.post(
            url, 
            headers=get_headers(access_token), 
            json=payload, 
            timeout=10
        )
        if response.status_code == 201:
            return response.json()
        print(f"GitHub create_pull_request error (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"GitHub create_pull_request exception: {e}")
    return None
