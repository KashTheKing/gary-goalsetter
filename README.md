# Gary Goalsetter

Discord bot for weekly goal tracking. Members set a goal with `/setgoal`, mark it complete on the board, and earn points at the Sunday reset.

## Commands

- `/setchannel` — set the channel Gary posts in
- `/setgoal` — set your goal for the week
- `/points` — check a member's points
- `/leaderboard` — top 5 point holders
- `/forcerefresh` — run the weekly review/reset now

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
