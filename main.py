### Imports
import discord
from discord.ext import commands
from discord.ext import tasks
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

load_dotenv()


### Data saving
DATA = "data.json"

def loadData():
    if os.path.exists(DATA):
        with open(DATA, 'r') as f:
            return json.load(f)
    return {'goals': {}, 'points': {}, 'channel_id': None, 'board_message_id': None}

def saveData():
    with open(DATA, 'w') as f:
        json.dump(data, f, indent = 4)

# Init data
data = loadData()
goals = data['goals']
points = data['points']
channel_id = data.get('channel_id')
board_message_id = data.get("board_message_id")


### Client
class Client(commands.Bot):
    async def on_ready(self):
        try:
            guild = discord.Object(id=1173015952816873502)
            synced = await self.tree.sync(guild=guild)
            print(f'Synced {len(synced)} commands to guild {guild.id}')
            weekly_reset.start()  # start Sunday reset loop
            await update_board(client)
        except Exception as err:
            print(f'Error syncing commands: {err}')



### Embed builders
def build_board():
    embed = discord.Embed(
        title = "📋 Weekly Goals Board",
        description = "Submit your goals with '/setgoal'!",
        color = discord.Color.red()
    )
    if not goals:
        embed.add_field(name = 'No goals yet wtf', value = 'Be the first to set one!', inline = False)
    else:
        for user_id, g in goals.items():
            status = "✅ Completed" if g["completed"] else "❌ In Progress"
            embed.add_field(
                name = '--------------------',
                value = f"<@{int(user_id)}>     |       **Goal:** {g['goal']}      |       **Status:** {status}",
                inline = False
            )
    embed.set_footer(text = 'Lets get to work, fellas! 💪')
    return embed


def build_review():
    embed = discord.Embed(
        title = f"📋 Weekly Goal Review | {datetime.now().strftime("%B %d, %Y")}",
        description = "Let's see how you all did...",
        color = discord.Color.green()
    )
    if not goals:
        embed.add_field(name = 'NO GOALS? TF ARE YOU GUYS DOING?', value = 'DO BETTER!', inline = False)
        embed.set_footer(text = 'Disappointed as shit fellas. Not okay.')
    else:
        for user_id, g in goals.items():
            status = "✅ They hit their goal!" if g["completed"] else "❌ They failed so fucking hard holy shit"
            embed.add_field(
                name = '--------------------',
                value = f"<@{int(user_id)}> wanted to **{g['goal'].lower()}...**\n{status}",
                inline = False
            )
        embed.set_footer(text = 'Keep it up, fellas! 💪')
    return embed



### Button
class GoalView(discord.ui.View):
    @discord.ui.button(label = "Mark as Complete ✔", style = discord.ButtonStyle.green)
    async def complete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id in goals:
            goals[user_id]["completed"] = True
            await interaction.response.edit_message(embed = build_board(), view = self)
        else:
            await interaction.response.send_message("You don’t have a goal set!", ephemeral = True)



### Update Board
async def update_board(bot: commands.Bot):
    if not channel_id: return

    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel): return

    global board_message_id
    if board_message_id:
        try:
            msg = await channel.fetch_message(board_message_id)
            await msg.edit(embed = build_board(), view = GoalView())
            return
        except discord.NotFound:
            board_message_id = None  # reset if message deleted

    # If no board exists, create one
    new_msg = await channel.send(embed = build_board(), view = GoalView())
    board_message_id = new_msg.id
    data["board_message_id"] = board_message_id
    saveData()



### Refresh
async def refresh():
    global board_message_id

    if channel_id:
            channel = client.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                # Post review board
                await channel.send(embed = build_review())
                await asyncio.sleep(5)

                # Delete old board if still active
                if board_message_id:
                    try:
                        old_msg = await channel.fetch_message(board_message_id)
                        await old_msg.delete()
                    except discord.NotFound:
                        pass
                    board_message_id = None

                # Add points
                for user_id, g in goals.items():
                    if g['completed'] == True:
                        points[user_id] = points.get(user_id, 0) + 1

                # Reset goals
                goals.clear()
                data['goals'] = {}
                data['board_message_id'] = None
                data['points'] = points
                saveData()

                await update_board(client)



### Setup
intents = discord.Intents.default()
intents.message_content = True
client = Client(command_prefix = '!', intents=intents)
GUILD_ID = discord.Object(id = 1173015952816873502)



### Commands

# Set channel for Gary to talk in
@client.tree.command(name = 'setchannel', description = 'Set the channel for Gary to post in', guild = GUILD_ID)
async def setChannel(interaction: discord.Interaction, channel: discord.TextChannel):
    global channel_id
    channel_id = channel.id
    data['channel_id'] = channel_id
    data["board_message_id"] = None
    saveData()

    await update_board(client)
    await interaction.response.send_message(f"Gary will now post in {channel.mention}", ephemeral = True)

# Set goal for the week
@client.tree.command(name = 'setgoal', description = 'Set a goal for the week', guild = GUILD_ID)
async def setGoal(interaction: discord.Interaction, goal: str):
    goals[str(interaction.user.id)] = {'goal': goal, 'completed': False}
    saveData()
    await update_board(client)
    await interaction.response.send_message(
        "Goal set!",
        ephemeral = True)

# Force show the board
@client.tree.command(name = 'forcerefresh', description = 'Run end of week command', guild = GUILD_ID)
async def forceRefresh(interaction: discord.Interaction):
    await interaction.response.send_message('Running command!', ephemeral = True)
    await refresh()

# Check your points
@client.tree.command(name = 'points', description = 'Check points of member', guild = GUILD_ID)
async def checkPoints(interaction: discord.Interaction, member: discord.Member):
    member = member or interaction.user
    total = points.get(str(member.id), 0)
    await interaction.response.send_message(
        f"{member.mention} has **{total}** points!",
        ephemeral = False
    )

# Display leaderboard command
@client.tree.command(name = 'leaderboard', description = 'Display points leaderboard', guild = GUILD_ID)
async def leaderboard(interaction: discord.Interaction):
    if not points: await interaction.response.send_message("Nobody has points!", ephemeral = True); return

    sortedPoints = sorted(points.items(), key = lambda x: x[1], reverse = True)[:5]

    embed = discord.Embed(
        title = "🏆 Gary's Little Stars!",
        description = "Top 5 members with the most points",
        color = discord.Color.gold()
    )

    for x, (user_id, score) in enumerate(sortedPoints, start = 1):
        user = client.get_user(int(user_id))
       
        embed.add_field(
                name = f"#{x}",
                value = f"<@{int(user_id)}> with {score} points!",
                inline = False,
            )

    embed.set_footer(text="Keep grinding those goals 💪")
    await interaction.response.send_message(embed=embed)



### Main Loop
@tasks.loop(minutes=60)
async def weekly_reset():
    now = datetime.now()

    # Sunday 18:00 UTC
    if now.weekday() == 6 and now.hour == 18:
        await refresh()



### Run
client.run(os.environ['DISCORD_TOKEN'])
