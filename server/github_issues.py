"""GitHub issue creation helper.

Called when a meeting participant types:
  CREATE ISSUE @me @github_username repo-name [optional title after repo name]

@me  → resolved to GITHUB_OWNER from .env (the admin / token holder)
@username → any additional GitHub user to assign
repo-name → repository under GITHUB_OWNER's account (or org/repo for cross-org repos)
"""

import os
import re
import urllib.request
import urllib.error
import json
from typing import Any


# Pattern: CREATE ISSUE @me @optionalUser repo-name optional title text
# Groups: (me_literal, extra_user_or_None, repo, title_or_empty)
ISSUE_COMMAND_RE = re.compile(
    r"(?i)CREATE\s+ISSUE\s+@me(?:\s+@([\w.\-]+))?\s+([\w.\-/]+)(?:\s+(.+))?",
    re.IGNORECASE,
)


def parse_issue_command(text: str) -> dict[str, Any] | None:
    """
    Returns a dict with keys: repo, assignees, title, body
    or None if the text does not match the command pattern.

    Examples that match:
      CREATE ISSUE @me @alice my-repo Fix login bug
      CREATE ISSUE @me my-org/my-repo
      CREATE ISSUE @me @bob some-repo Implement dark mode
    """
    match = ISSUE_COMMAND_RE.search(text.strip())
    if not match:
        return None

    extra_user: str | None = match.group(1)   # e.g. "alice"  (without @)
    repo: str = match.group(2).strip()        # e.g. "my-repo" or "org/repo"
    raw_title: str = (match.group(3) or "").strip()

    owner = os.getenv("GITHUB_OWNER", "")

    # If repo contains no slash, prepend owner so the API path is owner/repo
    if "/" not in repo:
        full_repo = f"{owner}/{repo}" if owner else repo
    else:
        full_repo = repo

    assignees = [owner] if owner else []
    if extra_user and extra_user not in assignees:
        assignees.append(extra_user)

    title = raw_title if raw_title else "New issue from meeting"

    return {
        "repo": full_repo,
        "assignees": assignees,
        "title": title,
        "body": (
            f"This issue was created automatically from a meeting chat command.\n\n"
            f"**Command:** `{text.strip()}`\n\n"
            f"**Assignees:** {', '.join('@' + a for a in assignees)}"
        ),
    }


def create_github_issue(
    repo: str,
    title: str,
    body: str,
    assignees: list[str],
) -> dict[str, Any]:
    """
    Creates a GitHub issue via the REST API.
    Returns the created issue object or raises on failure.
    """
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN is not set in .env")

    url = f"https://api.github.com/repos/{repo}/issues"
    payload = json.dumps({
        "title": title,
        "body": body,
        "assignees": assignees,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API returned {exc.code}: {error_body}"
        ) from exc


def handle_issue_command(text: str) -> dict[str, Any]:
    """
    Full pipeline: parse command → create issue → return result dict.
    Raises ValueError if the command is not recognised.
    Raises RuntimeError on GitHub API failure.
    """
    parsed = parse_issue_command(text)
    if parsed is None:
        raise ValueError(f"Not a valid CREATE ISSUE command: {text!r}")

    issue = create_github_issue(
        repo=parsed["repo"],
        title=parsed["title"],
        body=parsed["body"],
        assignees=parsed["assignees"],
    )

    return {
        "issue_number": issue.get("number"),
        "issue_url": issue.get("html_url"),
        "title": issue.get("title"),
        "repo": parsed["repo"],
        "assignees": parsed["assignees"],
    }
