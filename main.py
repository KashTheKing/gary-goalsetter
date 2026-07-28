### Imports
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
GUILD_ID = discord.Object(id=int(os.getenv('GUILD_ID', '1173015952816873502')))


### Database
# ponytail: sync sqlite3 — fine at server scale, swap to aiosqlite if it ever blocks
db = sqlite3.connect('gary.db')
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS goals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER, user_id INTEGER,
    description TEXT,
    deadline INTEGER,              -- unix ts, NULL = open-ended
    required INTEGER DEFAULT 1,    -- validations needed to complete
    cooldown INTEGER DEFAULT 600,  -- remind/notify cooldown, seconds
    channel_id INTEGER, message_id INTEGER,
    completed INTEGER DEFAULT 0,
    created INTEGER
);
CREATE TABLE IF NOT EXISTS validators(
    goal_id INTEGER, user_id INTEGER, validated INTEGER DEFAULT 0,
    whitelisted INTEGER DEFAULT 1,  -- 0 = ad-hoc validator on an open goal
    PRIMARY KEY(goal_id, user_id)
);
CREATE TABLE IF NOT EXISTS reminds(
    goal_id INTEGER, user_id INTEGER, last INTEGER,
    PRIMARY KEY(goal_id, user_id)
);
CREATE TABLE IF NOT EXISTS settings(
    guild_id INTEGER PRIMARY KEY, goals_channel INTEGER, notif_channel INTEGER
);
CREATE TABLE IF NOT EXISTS optins(
    guild_id INTEGER, user_id INTEGER, PRIMARY KEY(guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS points(
    guild_id INTEGER, user_id INTEGER, points INTEGER DEFAULT 0,
    PRIMARY KEY(guild_id, user_id)
);
""")
try:
    db.execute("ALTER TABLE validators ADD COLUMN whitelisted INTEGER DEFAULT 1")
except sqlite3.OperationalError:
    pass  # column already exists
db.commit()


def get_goal(goal_id: int):
    return db.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()


def get_setting(guild_id: int, col: str):
    row = db.execute("SELECT * FROM settings WHERE guild_id=?", (guild_id,)).fetchone()
    return row[col] if row else None


### Embed builder
def goal_embed(g) -> discord.Embed:
    vrows = db.execute("SELECT * FROM validators WHERE goal_id=?", (g['id'],)).fetchall()
    validated = sum(v['validated'] for v in vrows)
    embed = discord.Embed(
        title=f"🎯 Goal #{g['id']}",
        description=g['description'],
        color=discord.Color.green() if g['completed'] else discord.Color.red(),
    )
    embed.add_field(name="Owner", value=f"<@{g['user_id']}>")
    if g['deadline']:
        embed.add_field(name="Deadline", value=f"<t:{g['deadline']}:f> (<t:{g['deadline']}:R>)")
    if any(not v['whitelisted'] for v in vrows) or not vrows:
        # open goal: no whitelist, anyone can validate
        names = "\n".join(f"✅ <@{v['user_id']}>" for v in vrows if v['validated'])
        value = (names + "\n" if names else "") + "*Anyone can validate this goal.*"
    else:
        value = "\n".join(f"{'✅' if v['validated'] else '⬜'} <@{v['user_id']}>" for v in vrows)
    embed.add_field(name=f"Validation ({validated}/{g['required']})", value=value, inline=False)
    embed.set_footer(text="✅ Goal completed! 💪" if g['completed'] else "Hold them accountable, fellas 💪")
    return embed


### Goal buttons (persistent — survive restarts)
class GoalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def _goal(self, interaction):
        return db.execute(
            "SELECT * FROM goals WHERE message_id=?", (interaction.message.id,)
        ).fetchone()

    def _on_cooldown(self, goal, user_id: int) -> int:
        """Returns seconds remaining, 0 if free to act."""
        row = db.execute(
            "SELECT last FROM reminds WHERE goal_id=? AND user_id=?", (goal['id'], user_id)
        ).fetchone()
        if row:
            remaining = row['last'] + goal['cooldown'] - int(time.time())
            if remaining > 0:
                return remaining
        return 0

    def _stamp(self, goal, user_id: int):
        db.execute(
            "INSERT OR REPLACE INTO reminds VALUES (?,?,?)",
            (goal['id'], user_id, int(time.time())),
        )
        db.commit()

    @discord.ui.button(label="Remind 🔔", style=discord.ButtonStyle.primary, custom_id="goal_remind")
    async def remind(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self._goal(interaction)
        if not g or g['completed']:
            await interaction.response.send_message("This goal is no longer active.", ephemeral=True)
            return
        if interaction.user.id == g['user_id']:
            await interaction.response.send_message("You can't remind yourself. Get to work.", ephemeral=True)
            return
        remaining = self._on_cooldown(g, interaction.user.id)
        if remaining:
            await interaction.response.send_message(
                f"Cooldown — you can remind again in {remaining // 60}m {remaining % 60}s.", ephemeral=True
            )
            return
        self._stamp(g, interaction.user.id)
        text = (
            f"🔔 <@{g['user_id']}>, {interaction.user.mention} is reminding you of your goal: "
            f"**{g['description']}**"
        )
        # If a notifications channel is set and the owner opted in, remind there too
        notif_channel_id = get_setting(g['guild_id'], 'notif_channel')
        opted = db.execute(
            "SELECT 1 FROM optins WHERE guild_id=? AND user_id=?", (g['guild_id'], g['user_id'])
        ).fetchone()
        notif_channel = client.get_channel(notif_channel_id) if notif_channel_id and opted else None
        if isinstance(notif_channel, discord.TextChannel) and notif_channel.id != g['channel_id']:
            await notif_channel.send(text, embed=goal_embed(g))
        await interaction.response.send_message(text)

    @discord.ui.button(label="Copy 📋", style=discord.ButtonStyle.secondary, custom_id="goal_copy")
    async def copy(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self._goal(interaction)
        if not g:
            await interaction.response.send_message("Goal not found.", ephemeral=True)
            return
        await interaction.response.send_modal(GoalModal(copy_from=g))

    @discord.ui.button(label="Validate ✅", style=discord.ButtonStyle.green, custom_id="goal_validate")
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self._goal(interaction)
        if not g or g['completed']:
            await interaction.response.send_message("This goal is no longer active.", ephemeral=True)
            return
        if interaction.user.id == g['user_id']:
            await interaction.response.send_message("You can't validate your own goal.", ephemeral=True)
            return
        has_whitelist = db.execute(
            "SELECT 1 FROM validators WHERE goal_id=? AND whitelisted=1", (g['id'],)
        ).fetchone()
        row = db.execute(
            "SELECT * FROM validators WHERE goal_id=? AND user_id=?", (g['id'], interaction.user.id)
        ).fetchone()
        if has_whitelist and not row:
            await interaction.response.send_message("You're not a validator for this goal.", ephemeral=True)
            return
        if row and row['validated']:
            await interaction.response.send_message("You already validated this goal.", ephemeral=True)
            return
        db.execute(
            "INSERT INTO validators(goal_id, user_id, validated, whitelisted) VALUES (?,?,1,0) "
            "ON CONFLICT(goal_id, user_id) DO UPDATE SET validated=1",
            (g['id'], interaction.user.id),
        )
        count = db.execute(
            "SELECT COUNT(*) c FROM validators WHERE goal_id=? AND validated=1", (g['id'],)
        ).fetchone()['c']
        if count >= g['required']:
            db.execute("UPDATE goals SET completed=1 WHERE id=?", (g['id'],))
            db.execute(
                "INSERT INTO points VALUES (?,?,1) "
                "ON CONFLICT(guild_id,user_id) DO UPDATE SET points=points+1",
                (g['guild_id'], g['user_id']),
            )
        db.commit()
        g = get_goal(g['id'])
        await interaction.response.edit_message(embed=goal_embed(g), view=None if g['completed'] else self)
        if g['completed']:
            await interaction.followup.send(
                f"🎉 <@{g['user_id']}> completed their goal: **{g['description']}** (+1 point)"
            )


### Goal creation: modal → validator picker → post
class ValidatorPicker(discord.ui.View):
    def __init__(self, description, deadline, required, cooldown):
        super().__init__(timeout=300)
        self.description = description
        self.deadline = deadline
        self.required = required
        self.cooldown = cooldown

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Whitelist up to 5 validators (empty = anyone can validate)",
        min_values=0,
        max_values=5,
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        await interaction.response.defer()

    @discord.ui.button(label="Post Goal 🎯", style=discord.ButtonStyle.green)
    async def post(self, interaction: discord.Interaction, button: discord.ui.Button):
        validators = self.children[0].values
        goals_channel_id = get_setting(interaction.guild_id, 'goals_channel')
        channel = client.get_channel(goals_channel_id) if goals_channel_id else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "No goals channel set. An admin can set one with /setchannel.", ephemeral=True
            )
            return
        required = min(self.required, len(validators)) if validators else self.required
        cur = db.execute(
            "INSERT INTO goals(guild_id, user_id, description, deadline, required, cooldown,"
            " channel_id, created) VALUES (?,?,?,?,?,?,?,?)",
            (interaction.guild_id, interaction.user.id, self.description, self.deadline,
             required, self.cooldown, channel.id, int(time.time())),
        )
        goal_id = cur.lastrowid
        db.executemany(
            "INSERT INTO validators(goal_id, user_id) VALUES (?,?)",
            [(goal_id, u.id) for u in validators],
        )
        msg = await channel.send(embed=goal_embed(get_goal(goal_id)), view=GoalView())
        db.execute("UPDATE goals SET message_id=? WHERE id=?", (msg.id, goal_id))
        db.commit()
        who = f"{required}/{len(validators)} whitelisted" if validators else f"{required} (anyone)"
        await interaction.response.edit_message(
            content=f"Goal #{goal_id} posted in {channel.mention}! Needs {who} validations.",
            view=None,
        )


class GoalModal(discord.ui.Modal, title="New Goal"):
    description = discord.ui.TextInput(label="What's your goal?", max_length=200)

    def __init__(self, copy_from=None):
        super().__init__()
        if copy_from:
            self.description.default = copy_from['description']
            self.required.default = str(copy_from['required'])
            self.cooldown.default = format_duration(copy_from['cooldown'])

    deadline = discord.ui.TextInput(
        label="Deadline (optional)",
        placeholder="daily | YYYY-MM-DD | YYYY-MM-DD HH:MM (UTC)",
        required=False,
    )
    required = discord.ui.TextInput(
        label="Validations needed (default 1)", placeholder="e.g. 3", required=False
    )
    cooldown = discord.ui.TextInput(
        label="Remind cooldown (default 10m)",
        placeholder="e.g. 30 (seconds), 15m, 2hr, 1day, 1w",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            deadline = parse_deadline(str(self.deadline))
        except ValueError:
            await interaction.response.send_message(
                "Couldn't parse that deadline. Use `daily`, `YYYY-MM-DD`, or `YYYY-MM-DD HH:MM` (UTC).",
                ephemeral=True,
            )
            return
        req_s = str(self.required).strip()
        required = max(1, int(req_s)) if req_s.isdigit() else 1
        cd_s = str(self.cooldown).strip()
        try:
            cooldown = max(1, parse_duration(cd_s)) if cd_s else 600
        except ValueError:
            await interaction.response.send_message(
                "Couldn't parse that cooldown. Use e.g. `30` (seconds), `15m`, `2hr`, `1day`, `1w`.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Pick who can validate your goal (leave empty to let anyone validate):",
            view=ValidatorPicker(str(self.description), deadline, required, cooldown),
            ephemeral=True,
        )


DURATION_UNITS = {
    's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
    'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
    'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
    'd': 86400, 'day': 86400, 'days': 86400,
    'w': 604800, 'wk': 604800, 'week': 604800, 'weeks': 604800,
    'mo': 2592000, 'mon': 2592000, 'month': 2592000, 'months': 2592000,
    'y': 31536000, 'yr': 31536000, 'year': 31536000, 'years': 31536000,
}


def parse_duration(s: str) -> int:
    """'15' = 15s, '1m', '2hr', '1day', '1w', '1mo', '1y'. Raises ValueError."""
    match = re.fullmatch(r'(\d+)\s*([a-z]*)', s.strip().lower())
    if not match or (match[2] and match[2] not in DURATION_UNITS):
        raise ValueError(s)
    return int(match[1]) * DURATION_UNITS.get(match[2], 1)


def format_duration(seconds: int) -> str:
    for unit, size in (('w', 604800), ('day', 86400), ('hr', 3600), ('m', 60)):
        if seconds % size == 0 and seconds >= size:
            return f"{seconds // size}{unit}"
    return str(seconds)


def parse_deadline(s: str):
    s = s.strip().lower()
    if not s:
        return None
    now = datetime.now(timezone.utc)
    if s == 'daily':
        return int(now.replace(hour=23, minute=59, second=0, microsecond=0).timestamp())
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    raise ValueError(s)


### Paginated goal lists
PAGE_SIZE = 5


class GoalListView(discord.ui.View):
    def __init__(self, title: str, rows):
        super().__init__(timeout=300)
        self.title = title
        self.rows = rows
        self.page = 0
        self.pages = max(1, -(-len(rows) // PAGE_SIZE))
        self._sync_buttons()

    def _sync_buttons(self):
        self.children[0].disabled = self.page == 0
        self.children[1].disabled = self.page >= self.pages - 1

    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.title} (Page {self.page + 1}/{self.pages})",
            color=discord.Color.red(),
        )
        now = int(time.time())
        for g in self.rows[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE]:
            expired = g['deadline'] and g['deadline'] < now
            deadline = f" — {'⌛ expired' if expired else 'due'} <t:{g['deadline']}:R>" if g['deadline'] else ""
            embed.add_field(
                name=f"Goal #{g['id']}",
                value=f"<@{g['user_id']}>: {g['description']}{deadline}",
                inline=False,
            )
        embed.set_footer(text="Use /goal to view one, /copygoal to reuse one")
        return embed

    @discord.ui.button(label="◀ Last Page", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Next Page ▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.pages - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)


### Setup / welcome message
class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Server Setup 🛠", style=discord.ButtonStyle.primary, custom_id="setup_server")
    async def server_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Admins only (needs Manage Server).", ephemeral=True)
            return
        embed = discord.Embed(
            title="🛠 Server Setup",
            color=discord.Color.blurple(),
            description=(
                "1. `/setchannel #channel` — where goals get posted (done if you're reading this here!)\n"
                "2. `/setnotifchannel #channel` — reminders also get broadcast here for opted-in users\n\n"
                "That's it. Gary needs View Channel, Send Messages, and Embed Links in both channels."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="User Setup 👤", style=discord.ButtonStyle.secondary, custom_id="setup_user")
    async def user_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="👤 User Setup",
            color=discord.Color.blurple(),
            description=(
                "1. `/setgoal` — set your goal, an optional deadline, how many validations "
                "you need, and the remind cooldown\n"
                "2. Pick up to 5 people to validate your goal (e.g. need 3 of 5)\n"
                "3. `/notifications` — opt in so reminders also broadcast to the notifications channel\n\n"
                "On each goal: **Remind 🔔** pings the owner, **Validate ✅** is for the chosen "
                "validators — enough validations completes the goal and earns a point.\n"
                "Check progress with `/goals @member`, `/points`, and `/leaderboard`."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="New Goal 🎯", style=discord.ButtonStyle.green, custom_id="setup_newgoal")
    async def new_goal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GoalModal())

    @discord.ui.button(label="Goals 📜", style=discord.ButtonStyle.secondary, custom_id="setup_goals")
    async def server_goals(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = db.execute(
            "SELECT * FROM goals WHERE guild_id=? AND completed=0 ORDER BY id",
            (interaction.guild_id,),
        ).fetchall()
        if not rows:
            await interaction.response.send_message("No active goals in this server.", ephemeral=True)
            return
        view = GoalListView("🎯 Server goals", rows)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)


def welcome_embed(channel: discord.TextChannel) -> discord.Embed:
    return discord.Embed(
        title="🎯 Gary Goalsetter is set up!",
        color=discord.Color.green(),
        description=(
            f"Goals will now be posted in {channel.mention}.\n\n"
            "**What's Gary?** An accountability bot. You set a goal, pick friends to validate it, "
            "and the server holds you to it — Gary just keeps score. Goals stay up until enough "
            "of your chosen validators sign off, and completed goals earn points.\n\n"
            "Click a button below to get started."
        ),
    )


### Client
class Client(commands.Bot):
    async def setup_hook(self):
        self.add_view(GoalView())
        self.add_view(SetupView())
        self.tree.copy_global_to(guild=GUILD_ID)
        synced = await self.tree.sync(guild=GUILD_ID)
        print(f'Synced {len(synced)} commands')


client = Client(command_prefix='!', intents=discord.Intents.default())


### Commands
@client.tree.command(name='setgoal', description='Set a new goal')
async def new_goal(interaction: discord.Interaction):
    await interaction.response.send_modal(GoalModal())


@client.tree.command(name='goals', description="List a member's active goals (default: you)")
async def list_goals(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    rows = db.execute(
        "SELECT * FROM goals WHERE guild_id=? AND user_id=? AND completed=0 ORDER BY id",
        (interaction.guild_id, member.id),
    ).fetchall()
    if not rows:
        await interaction.response.send_message(f"{member.mention} has no active goals.", ephemeral=True)
        return
    view = GoalListView(f"🎯 Goals — {member.display_name}", rows)
    await interaction.response.send_message(embed=view.embed(), view=view)


@client.tree.command(name='copygoal', description='Create a new goal from an old one')
async def copy_goal(interaction: discord.Interaction, goal_id: int):
    g = get_goal(goal_id)
    if not g or g['guild_id'] != interaction.guild_id:
        await interaction.response.send_message("No such goal.", ephemeral=True)
        return
    await interaction.response.send_modal(GoalModal(copy_from=g))


@client.tree.command(name='goal', description="Show a specific goal's embed")
async def show_goal(interaction: discord.Interaction, member: discord.Member, goal_id: int):
    g = get_goal(goal_id)
    if not g or g['user_id'] != member.id or g['guild_id'] != interaction.guild_id:
        await interaction.response.send_message("No such goal for that member.", ephemeral=True)
        return
    jump = f"https://discord.com/channels/{g['guild_id']}/{g['channel_id']}/{g['message_id']}"
    await interaction.response.send_message(
        f"[Jump to goal message]({jump})", embed=goal_embed(g), ephemeral=True
    )


@client.tree.command(name='cancelgoal', description='Cancel one of your goals')
async def cancel_goal(interaction: discord.Interaction, goal_id: int):
    g = get_goal(goal_id)
    if not g or g['user_id'] != interaction.user.id:
        await interaction.response.send_message("That's not your goal.", ephemeral=True)
        return
    db.execute("DELETE FROM goals WHERE id=?", (goal_id,))
    db.execute("DELETE FROM validators WHERE goal_id=?", (goal_id,))
    db.execute("DELETE FROM reminds WHERE goal_id=?", (goal_id,))
    db.commit()
    channel = client.get_channel(g['channel_id'])
    if isinstance(channel, discord.TextChannel):
        try:
            msg = await channel.fetch_message(g['message_id'])
            await msg.delete()
        except discord.NotFound:
            pass
    await interaction.response.send_message(f"Goal #{goal_id} cancelled.", ephemeral=True)


@client.tree.command(name='setchannel', description='Set the goals channel (admin)')
@app_commands.default_permissions(manage_guild=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    db.execute(
        "INSERT INTO settings(guild_id, goals_channel) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET goals_channel=excluded.goals_channel",
        (interaction.guild_id, channel.id),
    )
    db.commit()
    await channel.send(embed=welcome_embed(channel), view=SetupView())
    await interaction.response.send_message(f"Goals will be posted in {channel.mention}.", ephemeral=True)


@client.tree.command(name='setnotifchannel', description='Set the notifications channel (admin)')
@app_commands.default_permissions(manage_guild=True)
async def set_notif_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    db.execute(
        "INSERT INTO settings(guild_id, notif_channel) VALUES (?,?) "
        "ON CONFLICT(guild_id) DO UPDATE SET notif_channel=excluded.notif_channel",
        (interaction.guild_id, channel.id),
    )
    db.commit()
    await interaction.response.send_message(f"Notifications will go to {channel.mention}.", ephemeral=True)


@client.tree.command(name='notifications', description='Opt in/out of goal notifications')
async def notifications(interaction: discord.Interaction):
    opted = db.execute(
        "SELECT 1 FROM optins WHERE guild_id=? AND user_id=?",
        (interaction.guild_id, interaction.user.id),
    ).fetchone()
    if opted:
        db.execute(
            "DELETE FROM optins WHERE guild_id=? AND user_id=?",
            (interaction.guild_id, interaction.user.id),
        )
        text = "You've opted **out** of goal notifications."
    else:
        db.execute(
            "INSERT INTO optins VALUES (?,?)", (interaction.guild_id, interaction.user.id)
        )
        text = "You've opted **in** to goal notifications."
    db.commit()
    await interaction.response.send_message(text, ephemeral=True)


@client.tree.command(name='points', description="Check a member's points")
async def check_points(interaction: discord.Interaction, member: discord.Member):
    row = db.execute(
        "SELECT points FROM points WHERE guild_id=? AND user_id=?",
        (interaction.guild_id, member.id),
    ).fetchone()
    total = row['points'] if row else 0
    await interaction.response.send_message(f"{member.mention} has **{total}** points!")


@client.tree.command(name='leaderboard', description='Display points leaderboard')
async def leaderboard(interaction: discord.Interaction):
    rows = db.execute(
        "SELECT user_id, points FROM points WHERE guild_id=? ORDER BY points DESC LIMIT 5",
        (interaction.guild_id,),
    ).fetchall()
    if not rows:
        await interaction.response.send_message("Nobody has points!", ephemeral=True)
        return
    embed = discord.Embed(
        title="🏆 Gary's Little Stars!",
        description="Top 5 members with the most points",
        color=discord.Color.gold(),
    )
    for rank, row in enumerate(rows, start=1):
        embed.add_field(name=f"#{rank}", value=f"<@{row['user_id']}> with {row['points']} points!", inline=False)
    embed.set_footer(text="Keep grinding those goals 💪")
    await interaction.response.send_message(embed=embed)


### Run
client.run(os.environ['DISCORD_TOKEN'])
