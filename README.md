# Gary Goalsetter

Discord accountability bot. You set a goal, pick friends to validate it, and the server holds you to it — Gary just keeps score.

## How it works

1. `/setgoal` opens a modal: goal, optional deadline (`daily`, `YYYY-MM-DD`, or `YYYY-MM-DD HH:MM` UTC), how many validations you need, and the remind cooldown (default 10 min).
2. You pick up to 5 validators (e.g. need 3 of 5 to sign off).
3. The goal is posted as an embed in the goals channel with three buttons:
   - **Remind 🔔** — anyone (but you) pings you about your goal, rate-limited per person by your goal's cooldown.
   - **Validate ✅** — only your chosen validators can click; when enough do, the goal completes and you earn a point.
     If the owner opted in (`/notifications`) and a notifications channel is set, the reminder is broadcast there too.

Goals live in a local SQLite database (`gary.db`) and buttons keep working across restarts.

## Commands

- `/setgoal` — create a goal
- `/goals @member` — list a member's active goals
- `/goal @member goal-id` — show one goal's embed with a jump link
- `/cancelgoal goal-id` — cancel your own goal
- `/notifications` — opt in/out of reminder broadcasts to the notifications channel
- `/points @member`, `/leaderboard` — the score
- `/setchannel`, `/setnotifchannel` — admin: pick the goals / notifications channels

## Setup

```
pip install -r requirements.txt
```

Create a `.env` file:

```
DISCORD_TOKEN=your-bot-token
```

Run:

```
python main.py
```

## Authors

- KashTheKing
- DuckableDev
