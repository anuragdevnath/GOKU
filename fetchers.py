"""
fetchers.py

Shared GitHub + Gmail + Slack + Google Chat fetching logic, used by both
activity_report.py (CLI) and app.py (web UI).
"""

import datetime as dt
import os
import sys
from collections import defaultdict

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME")  # optional, auto-detected if unset

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_CREDENTIALS_FILE = "credentials.json"
GMAIL_TOKEN_FILE = "token.json"

SLACK_TOKEN = os.environ.get("SLACK_USER_TOKEN")  # xoxp-... user token

GOOGLE_CHAT_SCOPES = [
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.readonly",
]
GOOGLE_CHAT_CREDENTIALS_FILE = "credentials.json"  # same OAuth client as Gmail is fine
GOOGLE_CHAT_TOKEN_FILE = "chat_token.json"
# Optional: your Chat "users/xxxxxxxx" resource id, if you want to filter
# messages down to only the ones you sent (see README for how to find it).
GOOGLE_CHAT_USER_ID = os.environ.get("GOOGLE_CHAT_USER_ID")


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def github_get_username():
    if GITHUB_USERNAME:
        return GITHUB_USERNAME
    resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
    )
    resp.raise_for_status()
    return resp.json()["login"]


def github_fetch_events(username, start_date, end_date):
    """Returns a dict: {date_str: [event_dict, ...]}"""
    events = defaultdict(list)
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    date_range = f"{start_date}..{end_date}"

    pr_query = f"type:pr author:{username} created:{date_range}"
    _merge(events, _github_search(headers, "issues", pr_query, "PR opened"))

    issue_query = f"type:issue author:{username} created:{date_range}"
    _merge(events, _github_search(headers, "issues", issue_query, "Issue opened"))

    commit_query = f"author:{username} committer-date:{date_range}"
    _merge(events, _github_search_commits(headers, commit_query))

    return events


def _github_search(headers, endpoint, query, label):
    out = defaultdict(list)
    url = f"https://api.github.com/search/{endpoint}"
    page = 1
    while True:
        resp = requests.get(url, headers=headers, params={"q": query, "per_page": 100, "page": page})
        if resp.status_code != 200:
            print(f"  [github] warning: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
            break
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            date_str = item["created_at"][:10]
            out[date_str].append({
                "type": label,
                "title": item["title"],
                "repo": item["repository_url"].split("/repos/")[-1],
                "url": item["html_url"],
            })
        if len(items) < 100:
            break
        page += 1
    return out


def _github_search_commits(headers, query):
    out = defaultdict(list)
    url = "https://api.github.com/search/commits"
    commit_headers = dict(headers)
    commit_headers["Accept"] = "application/vnd.github.cloak-preview+json"
    page = 1
    while True:
        resp = requests.get(url, headers=commit_headers, params={"q": query, "per_page": 100, "page": page})
        if resp.status_code != 200:
            print(f"  [github] warning (commits): {resp.status_code} {resp.text[:200]}", file=sys.stderr)
            break
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            date_str = item["commit"]["committer"]["date"][:10]
            message = item["commit"]["message"].split("\n")[0]
            out[date_str].append({
                "type": "Commit",
                "title": message,
                "repo": item["repository"]["full_name"],
                "url": item["html_url"],
            })
        if len(items) < 100:
            break
        page += 1
    return out


def _merge(target, source):
    for k, v in source.items():
        target[k].extend(v)


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

def gmail_get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GMAIL_CREDENTIALS_FILE):
                print(
                    f"  [gmail] {GMAIL_CREDENTIALS_FILE} not found — skipping Gmail.",
                    file=sys.stderr,
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def gmail_fetch_events(start_date, end_date):
    """Returns a dict: {date_str: [event_dict, ...]}"""
    events = defaultdict(list)
    service = gmail_get_service()
    if service is None:
        return events

    start_fmt = start_date.replace("-", "/")
    end_fmt = (dt.date.fromisoformat(end_date) + dt.timedelta(days=1)).isoformat().replace("-", "/")
    query = f"after:{start_fmt} before:{end_fmt}"

    page_token = None
    all_msgs = []
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, pageToken=page_token, maxResults=500
        ).execute()
        all_msgs.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    for m in all_msgs:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From", "To", "Date"],
        ).execute()
        headers_list = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        internal_ts = int(msg.get("internalDate", "0")) / 1000
        date_str = dt.datetime.fromtimestamp(internal_ts).strftime("%Y-%m-%d")
        label_ids = msg.get("labelIds", [])
        direction = "Sent" if "SENT" in label_ids else "Received"
        events[date_str].append({
            "type": f"Email {direction}",
            "title": headers_list.get("Subject", "(no subject)"),
            "repo": headers_list.get("From" if direction == "Received" else "To", ""),
            "url": f"https://mail.google.com/mail/u/0/#all/{m['id']}",
        })

    return events


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
# NOTE: this used to rely on search.messages, but Slack's search API is a
# fuzzy relevance index, not a completeness guarantee — and its "to:"
# modifier only covers direct messages, not messages you received in
# channels. So instead this walks your actual conversation history (the
# same way the Gmail fetcher walks your inbox), which reliably returns
# every message in every conversation you're part of, then classifies each
# one as sent-by-you or received based on the sender's user ID.

def slack_get_user_id(headers):
    resp = requests.post("https://slack.com/api/auth.test", headers=headers)
    data = resp.json()
    if not data.get("ok"):
        print(f"  [slack] warning (auth.test): {data.get('error', 'unknown error')}", file=sys.stderr)
        return None
    return data.get("user_id")


def _slack_list_conversations(headers):
    """All channels, private channels, group DMs and 1:1 DMs you're a member of."""
    conversations = []
    cursor = None
    while True:
        params = {"types": "public_channel,private_channel,mpim,im", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get("https://slack.com/api/conversations.list", headers=headers, params=params)
        data = resp.json()
        if not data.get("ok"):
            print(f"  [slack] warning (conversations.list): {data.get('error', 'unknown error')}", file=sys.stderr)
            break
        conversations.extend(data.get("channels", []))
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return conversations


def _slack_conversation_label(headers, conv, name_cache):
    """A human-readable label for a channel/group/DM."""
    if conv.get("name"):
        return f"#{conv['name']}"
    if conv.get("is_im"):
        other_id = conv.get("user", "")
        if other_id not in name_cache:
            resp = requests.get("https://slack.com/api/users.info", headers=headers, params={"user": other_id})
            data = resp.json()
            if data.get("ok"):
                profile = data["user"].get("profile", {})
                name_cache[other_id] = profile.get("display_name") or profile.get("real_name") or other_id
            else:
                name_cache[other_id] = other_id
        return f"DM: {name_cache[other_id]}"
    return f"conversation {conv.get('id', 'unknown')}"


# Subtypes that are system events, not things a person actually "sent"
_SLACK_SKIP_SUBTYPES = {
    "channel_join", "channel_leave", "channel_topic", "channel_purpose",
    "channel_name", "channel_archive", "channel_unarchive", "bot_add",
    "bot_remove", "pinned_item", "unpinned_item",
}


def slack_fetch_events(start_date, end_date):
    """
    Returns a dict: {date_str: [event_dict, ...]}

    Walks real history for every channel/DM you're in, so both directions
    are covered:
      - "Slack sent"     — messages where you're the sender
      - "Slack received" — messages from anyone else, in conversations
                            you're part of

    Requires these User Token Scopes (in addition to search:read, which is
    no longer used but harmless to leave enabled):
    channels:history, groups:history, mpim:history, im:history,
    channels:read, groups:read, mpim:read, im:read, users:read
    """
    events = defaultdict(list)
    if not SLACK_TOKEN:
        print("  [slack] SLACK_USER_TOKEN env var not set — skipping Slack.", file=sys.stderr)
        return events

    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    user_id = slack_get_user_id(headers)
    if not user_id:
        return events

    start_ts = dt.datetime.fromisoformat(start_date).timestamp()
    end_ts = (dt.datetime.fromisoformat(end_date) + dt.timedelta(days=1)).timestamp()

    conversations = _slack_list_conversations(headers)
    name_cache = {}

    for conv in conversations:
        if conv.get("is_archived"):
            continue
        conv_id = conv["id"]
        label = _slack_conversation_label(headers, conv, name_cache)

        cursor = None
        while True:
            params = {
                "channel": conv_id,
                "oldest": f"{start_ts:.6f}",
                "latest": f"{end_ts:.6f}",
                "limit": 200,
                "inclusive": "true",
            }
            if cursor:
                params["cursor"] = cursor
            resp = requests.get("https://slack.com/api/conversations.history", headers=headers, params=params)
            data = resp.json()
            if not data.get("ok"):
                # not_in_channel / missing_scope for channels you can technically
                # see but haven't joined — skip quietly rather than spamming warnings
                err = data.get("error", "unknown error")
                if err not in ("not_in_channel", "channel_not_found"):
                    print(f"  [slack] warning on {label}: {err}", file=sys.stderr)
                break

            for m in data.get("messages", []):
                if m.get("subtype") in _SLACK_SKIP_SUBTYPES:
                    continue
                sender = m.get("user", "")
                if not sender:
                    continue  # skip bot/system messages with no user
                ts = float(m["ts"])
                date_str = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                text = (m.get("text") or "").replace("\n", " ")
                if len(text) > 140:
                    text = text[:140] + "..."
                direction = "Slack sent" if sender == user_id else "Slack received"
                events[date_str].append({
                    "type": direction,
                    "title": text or "(no text — attachment or file)",
                    "repo": label,
                    "url": "",
                })

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    return events


# ---------------------------------------------------------------------------
# Google Chat
# ---------------------------------------------------------------------------

def google_chat_get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(GOOGLE_CHAT_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GOOGLE_CHAT_TOKEN_FILE, GOOGLE_CHAT_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GOOGLE_CHAT_CREDENTIALS_FILE):
                print(
                    f"  [chat] {GOOGLE_CHAT_CREDENTIALS_FILE} not found — skipping Google Chat.",
                    file=sys.stderr,
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CHAT_CREDENTIALS_FILE, GOOGLE_CHAT_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GOOGLE_CHAT_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("chat", "v1", credentials=creds)


def google_chat_fetch_events(start_date, end_date):
    """
    Returns a dict: {date_str: [event_dict, ...]}

    NOTE: the Chat API doesn't offer a simple "messages sent by me" filter
    out of the box — it filters by createTime, not sender. By default this
    pulls every message in every space you're a member of within the date
    range (i.e. chat activity in your spaces, not strictly "sent by you").
    If you know your own Chat resource id (see README), set it as
    GOOGLE_CHAT_USER_ID to narrow results to just your own messages.
    """
    events = defaultdict(list)
    service = google_chat_get_service()
    if service is None:
        return events

    start_iso = f"{start_date}T00:00:00Z"
    end_iso = (dt.date.fromisoformat(end_date) + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"

    spaces = []
    page_token = None
    while True:
        resp = service.spaces().list(pageSize=100, pageToken=page_token).execute()
        spaces.extend(resp.get("spaces", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    for space in spaces:
        space_name = space.get("name")
        space_label = space.get("displayName") or space_name
        msg_page_token = None
        while True:
            try:
                resp = service.spaces().messages().list(
                    parent=space_name,
                    pageSize=100,
                    pageToken=msg_page_token,
                    filter=f'createTime > "{start_iso}" AND createTime < "{end_iso}"',
                ).execute()
            except Exception as exc:
                print(f"  [chat] warning on space {space_label}: {exc}", file=sys.stderr)
                break

            for m in resp.get("messages", []):
                sender = m.get("sender", {}).get("name", "")
                if GOOGLE_CHAT_USER_ID and sender != GOOGLE_CHAT_USER_ID:
                    continue
                create_time = m.get("createTime", "")
                date_str = create_time[:10]
                if not date_str:
                    continue
                text = (m.get("text") or "").replace("\n", " ")
                if len(text) > 140:
                    text = text[:140] + "..."
                events[date_str].append({
                    "type": "Google Chat message",
                    "title": text or "(no text — attachment or card)",
                    "repo": space_label,
                    "url": "",
                })

            msg_page_token = resp.get("nextPageToken")
            if not msg_page_token:
                break

    return events


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def daterange(start_date, end_date):
    d = dt.date.fromisoformat(start_date)
    end = dt.date.fromisoformat(end_date)
    while d <= end:
        yield d.isoformat()
        d += dt.timedelta(days=1)


def is_weekend(date_str):
    return dt.date.fromisoformat(date_str).weekday() >= 5  # 5=Sat, 6=Sun


def fetch_all(start_date, end_date, skip_github=False, skip_gmail=False,
              skip_slack=False, skip_chat=False):
    """
    Returns {date_str: {"is_weekend": bool, "events": [event, ...]}}
    for every day in the range, even days with no events.
    """
    all_events = defaultdict(list)

    if not skip_github:
        if not GITHUB_TOKEN:
            print("GITHUB_TOKEN env var not set — skipping GitHub.", file=sys.stderr)
        else:
            username = github_get_username()
            _merge(all_events, github_fetch_events(username, start_date, end_date))

    if not skip_gmail:
        _merge(all_events, gmail_fetch_events(start_date, end_date))

    if not skip_slack:
        _merge(all_events, slack_fetch_events(start_date, end_date))

    if not skip_chat:
        _merge(all_events, google_chat_fetch_events(start_date, end_date))

    result = {}
    for day in daterange(start_date, end_date):
        result[day] = {
            "is_weekend": is_weekend(day),
            "events": all_events.get(day, []),
        }
    return result
