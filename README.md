# GOKU — Get Only Key Updates

Shows what you did on GitHub, Gmail, Slack, and Google Chat for each day in
a date range — either as a terminal printout or in a local browser UI with
a calendar picker. Weekends (Sat/Sun) are labeled "Weekend / Week Off" but
still show any activity that happened, in case you worked.

Works on macOS, Windows, and Linux. Commands below are given for both
macOS/Linux (bash/zsh) and Windows (PowerShell) — use whichever matches
your machine.

## 0. Setting environment variables (reference for every step below)

This tool needs a few secret tokens (GitHub, Slack, etc). Each one gets
stored as an **environment variable** so it's available to the script
without being hardcoded anywhere. Whenever a step below says "set X as an
environment variable," come back to this section.

**macOS / Linux (zsh, the Terminal.app default):**

```bash
echo 'export VAR_NAME=your_value_here' >> ~/.zshrc
source ~/.zshrc
```

(If your shell is bash instead of zsh, use `~/.bash_profile` instead of
`~/.zshrc`. Check with `echo $SHELL`.)

**Windows (PowerShell):**

```powershell
[Environment]::SetEnvironmentVariable("VAR_NAME", "your_value_here", "User")
```

This sets it permanently, but you need to **close and reopen PowerShell**
for it to take effect in a new window. To set it just for your *current*
PowerShell session instead (temporary, lost when you close the window):

```powershell
$env:VAR_NAME="your_value_here"
```

Verify it's set (either OS, once you've opened a fresh terminal):

```bash
echo $VAR_NAME          # macOS/Linux
```
```powershell
echo $env:VAR_NAME       # Windows PowerShell
```

## 1. Install dependencies

**macOS / Linux:**

```bash
pip3 install flask requests google-auth google-auth-oauthlib google-api-python-client
```

**Windows:**

```powershell
pip install flask requests google-auth google-auth-oauthlib google-api-python-client
```

(Windows' official Python installer sets up `python`/`pip` directly; macOS
needs `python3`/`pip3` unless you're inside an activated virtual
environment — see the optional venv note at the bottom of this section.)

<details>
<summary>Optional: using a virtual environment</summary>

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script with an execution-policy error,
run this once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Once activated, `python`/`pip` work the same way on both platforms for the
rest of these steps.
</details>

## 2. GitHub setup

1. Go to https://github.com/settings/tokens → **Generate new token (classic)**
2. Check the `repo` scope
3. Set an expiration, generate, and copy the token
4. Set it as an environment variable named `GITHUB_TOKEN` (see section 0 above)

## 3. Gmail setup

1. https://console.cloud.google.com/ → create/select a project
2. Enable the **Gmail API** (APIs & Services → Library)
3. Configure the OAuth consent screen (External, add yourself as a test user)
4. Credentials → Create Credentials → OAuth client ID → **Desktop app**
5. Download the JSON, save it as `credentials.json` in this same folder
   (see `credentials.example.json` in this repo for the shape it should
   have — never commit your real one)
6. First run opens a browser to approve read-only access; a `token.json`
   is cached afterward so you won't need to log in again

Since this uses your own OAuth client rather than a shared published app,
Google will show an "unverified app" warning the first time you log in —
that's expected for a personal tool like this, just click through it
(Advanced → Go to [app name], since you're the one who made it).

## 4. Slack setup

Slack needs a **user token** (not a bot token) so it can read messages in
channels and DMs you're a member of.

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Give it a name (e.g. "GOKU") and pick your workspace
3. In the left sidebar: **OAuth & Permissions**
4. Scroll to **User Token Scopes** (not Bot Token Scopes) and add all of these:
   - `channels:history`
   - `groups:history`
   - `mpim:history`
   - `im:history`
   - `channels:read`
   - `groups:read`
   - `mpim:read`
   - `im:read`
   - `users:read`
5. Scroll up and click **Install to Workspace**, then approve it
6. Copy the **User OAuth Token** (starts with `xoxp-`)
7. Set it as an environment variable named `SLACK_USER_TOKEN` (see section 0)

If you'd already created the app with fewer scopes, go back to **OAuth &
Permissions**, add the scopes above, then click **Reinstall to Workspace**
— adding scopes doesn't take effect until you reinstall, and you'll get a
new token you need to copy over.

Note: this reads real conversation history (not just search), so it walks
every channel, group and DM you're a member of. Workspace admins can see
this app was installed, in case that matters for a work Slack.

## 5. Google Chat setup

This reuses the same `credentials.json` OAuth client you made for Gmail,
just with a separate login and token file, since the permissions
("scopes") are different.

1. In the same Google Cloud project as Gmail: enable the **Google Chat API**
   (APIs & Services → Library → search "Google Chat API" → Enable)
2. Nothing else to create — it uses your existing `credentials.json`
3. First run will open a browser again, this time asking you to approve
   Chat access. It caches a separate `chat_token.json`.

**Important limitation:** Google's Chat API can filter messages by date,
but not natively by "messages I sent" — so by default this shows *all*
messages in every space you're part of within the date range, not just
yours. If you want it narrowed to only your messages, find your Chat user
ID (open Google Chat in a browser, click your own profile picture on a
message you sent, and the URL/API inspector will show something like
`users/107...`) and set it as an environment variable named
`GOOGLE_CHAT_USER_ID` (see section 0).

Without it, treat the Chat results as "activity in my spaces" rather than
strictly "sent by me."

## 6. Run it

### Option A: Browser UI (recommended)

**macOS / Linux:**
```bash
python3 app.py
```

**Windows:**
```powershell
python app.py
```

Then open **http://127.0.0.1:5050** in your browser. Pick a start and end
date from the calendar pickers, optionally skip any of the four sources,
and click **Fetch activity**. Weekend days are highlighted and tagged
automatically.

This only runs on your own machine — nothing is exposed to the internet.

### Option B: Command line

**macOS / Linux:**
```bash
python3 activity_report.py --start 2026-09-20 --end 2026-09-25
```

**Windows:**
```powershell
python activity_report.py --start 2026-09-20 --end 2026-09-25
```

Flags: `--skip-github`, `--skip-gmail`, `--skip-slack`, `--skip-chat`

## Project structure

```
activity-tracker/
├── fetchers.py          # shared GitHub + Gmail + Slack + Chat fetching logic
├── activity_report.py   # CLI entry point
├── app.py                # Flask web server (UI entry point)
├── templates/
│   └── index.html        # calendar picker + results page
├── credentials.json       # you provide this (Google OAuth client, Gmail + Chat)
├── token.json              # auto-created after first Gmail login
└── chat_token.json         # auto-created after first Google Chat login
```

## What it pulls

**GitHub** (via the Search API, across all repos you have access to):
- Commits authored by you, by commit date
- Pull requests you opened
- Issues you opened

**Gmail**:
- Emails sent and received each day, with subject + counterpart

**Slack**:
- Messages you sent, across channels/DMs you're in ("Slack sent")
- Messages anyone else sent, in any channel/DM you're a member of
  ("Slack received") — this reads real history, not a search index, so it's
  complete rather than best-effort

**Google Chat**:
- Messages in spaces you're part of within the date range (see the
  limitation note above about narrowing this to just your own messages)

## Notes / next steps

- Weekends still fetch and display data — they're just visually flagged,
  not skipped, so a Saturday deploy or late-night message still shows up.
- GitHub's commit search index can lag a few minutes for very recent commits.
- Slack walks real conversation history rather than search, so it's slower
  on a wide date range or in a workspace with a lot of channels — give it
  a bit of time on first run.
- For a nicer written summary, pipe the day's events into an LLM prompt
  ("write me a one-paragraph standup update from this list") — happy to
  wire that into the UI as an extra button if useful.
