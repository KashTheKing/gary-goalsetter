# Gary Goalsetter

<img src="Gary%20Goalsetter.png" alt="Gary Goalsetter" width="200">

Discord accountability bot. You set a goal, pick friends to validate it, and the server holds you to it — Gary just keeps score.

## Add Gary to your server

Don't want to host your own? [Invite the official bot](https://discord.com/oauth2/authorize?client_id=1418733344430231565&permissions=85008&integration_type=0&scope=bot+applications.commands), then run `/setup` in your server.

## How it works

1. An admin runs `/setup` (or `/setchannel` + `/setnotifchannel`) to pick or create the channels.
2. `/setgoal` opens a modal:
   - **Goal** — what you're committing to.
   - **Deadline** (optional) — `daily` (end of today), `YYYY-MM-DD`, or `YYYY-MM-DD HH:MM` (UTC). Deadlines are informational; a goal only completes when validated. Past-deadline goals show as ⌛ expired.
   - **Validations needed** — how many sign-offs complete the goal (default 1).
   - **Remind cooldown** — how often each person can remind you. Formats: bare number = seconds (`30`), or `15m`, `2hr`, `1day`, `1w`, `1mo`, `1y` (default `10m`).
3. Next, whitelist up to 5 validators (e.g. require 3 of 5). **Leave it empty and anyone in the server can validate.**
4. The goal is posted as an embed in the goals channel with three buttons:
   - **Remind 🔔** — anyone (except you) pings you about your goal, rate-limited per person by your goal's cooldown. If you've opted into notifications and a notifications channel is set, the reminder is broadcast there too.
   - **Validate ✅** — whitelisted validators (or anyone, if open) sign off. You can't validate your own goal. When enough validations land, the goal turns green, buttons are removed, a 🎉 announcement is posted, and you earn **1 point per required validation** (a 3-validation goal pays 3 points).
   - **Copy 📋** — opens the goal modal pre-filled with that goal's text, validation count, and cooldown (deadline left blank) so anyone can reuse it.

Everything is stored per-server in a local SQLite database (`gary.db`); buttons keep working across bot restarts.

## Commands

### Goals

| Command | What it does |
|---|---|
| `/setgoal` | Create a goal via the modal + validator picker |
| `/goals [@member]` | Paginated list (5 per page, ◀/▶ buttons) of active goals — yours if no member given; expired ones tagged ⌛ |
| `/goal @member goal-id` | One goal's embed with a jump link to its message (ephemeral) |
| `/copygoal goal-id` | New goal pre-filled from an old one (works on completed goals too) |
| `/cancelgoal goal-id` | Cancel your own goal and delete its message |

### Points

| Command | What it does |
|---|---|
| `/points @member` | A member's point total |
| `/leaderboard` | Top 10 with 🥇🥈🥉 medals; footer shows your own total if you're not on the board |

### Notifications

| Command | What it does |
|---|---|
| `/notifications` | Toggle whether Remind 🔔 also broadcasts your reminders to the notifications channel |

### Admin (need Manage Server)

| Command | What it does |
|---|---|
| `/setup [goals_channel] [notif_channel]` | One-shot setup. Omitted channels are created: **#goals** (read-only for members) and **#goal-notifications** (open to all). Posts both panels. |
| `/setchannel #channel` | Set just the goals channel (posts the welcome panel) |
| `/setnotifchannel #channel` | Set just the notifications channel (posts the notifications panel) |
| `/deletegoal goal-id` | Delete any goal in the server |
| `/deletegoals @member` | Delete **all** of a member's goals |
| `/resetleaderboard` | Reset every member's points to 0 and restart tracking |

### Misc

| Command | What it does |
|---|---|
| `/ping` | Latency check — 🏓 Pong! |

## Panels

- **Welcome panel** (posted in the goals channel): explains the bot, with **Server Setup 🛠** (admin help), **User Setup 👤** (user walkthrough), **New Goal 🎯** (opens the goal modal), and **Goals 📜** (ephemeral paginated list of all server goals).
- **Notifications panel** (posted in the notifications channel): **New Goal 🎯**, **Goals 📜**, and **Opt In 🔔** / **Opt Out 🔕** buttons for reminder broadcasts.

## Self-hosting

```
pip install -r requirements.txt
```

Create a `.env` file:

```
DISCORD_TOKEN=your-bot-token
```

Optionally add `GUILD_ID=your-server-id` to sync commands to one server instantly (for testing); without it, commands sync globally (first propagation can take up to an hour).

Run:

```
python main.py
```

The bot needs these permissions: View Channels, Send Messages, Embed Links, Read Message History, and Manage Channels (only for `/setup` channel creation) — invite permissions integer `85008`.

## Authors

- KashTheKing
- DuckableDev
