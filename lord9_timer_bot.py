import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta, time
import pytz
from dotenv import load_dotenv
from keep_alive import keep_alive
keep_alive()

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ------------------------- INTENTS -------------------------
intents = discord.Intents.default()
intents.message_content = True  # Important para mo-detect ang commands
bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------- CONSTANTS -------------------------
DATA_FILE = "boss_data.json"
PH_TZ = pytz.timezone("Asia/Manila")

# Normal respawn bosses in hours
BOSS_RESPAWN = {
    "venatus": 10,
    "viorent": 10,
    "ego": 21,
    "livera": 24,
    "araneo": 24,
    "undomiel": 24,
    "ladydalia": 18,
    "general": 29,
    "amentis": 29,
    "baron": 32,
    "wannitas": 48,
    "metus": 48,
    "duplican": 48,
    "shuliar": 35,
    "gareth": 32,
    "titore": 37,
    "larba": 35,
    "catena": 35,
    "secreta": 62,
    "ordo": 62,
    "asta": 62,
    "supore": 62,
}

# Fixed schedule bosses using HH:MM strings
FIXED_SCHEDULE = {
    "clemantis": {"days_hours": {"monday": "11:30", "thursday": "19:00"}},
    "saphirus": {"days_hours": {"sunday": "17:00", "tuesday": "11:30"}},
    "neutro": {"days_hours": {"tuesday": "19:00", "thursday": "11:30"}},
    "thymele": {"days_hours": {"monday": "19:00", "wednesday": "11:30"}},
    "milavy": {"days_hours": {"saturday": "15:00"}},
    "ringor": {"days_hours": {"saturday": "17:00"}},
    "roderick": {"days_hours": {"friday": "19:00"}},
    "auraq": {"days_hours": {"friday": "22:00", "wednesday": "21:00"}},
    "chaiflock": {"days_hours": {"saturday": "22:00"}},
    "benji": {"days_hours": {"sunday": "21:00"}},
}

# Optional: channel ID for auto announcements
ALERT_CHANNEL_ID = None  # Replace with your channel ID if needed

# ------------------------- FILE STORAGE -------------------------
def get_data_file(ctx=None, guild_id=None):
    if ctx:
        gid = ctx.guild.id
    else:
        gid = guild_id
    return f"boss_data_{gid}.json"

def load_data(ctx=None, guild_id=None):
    file = get_data_file(ctx, guild_id)
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_data(data, ctx=None, guild_id=None):
    file = get_data_file(ctx, guild_id)
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# ------------------------- FIXED SCHEDULE CALC -------------------------
def get_next_fixed_spawn(days_hours):
    """Return next spawn datetime based on days_hours dict"""
    now = datetime.now(PH_TZ)
    next_spawn = None

    for i in range(7):
        check_date = now + timedelta(days=i)
        weekday = check_date.strftime("%A").lower()
        if weekday in days_hours:
            hh_mm = days_hours[weekday].split(":")
            hour = int(hh_mm[0])
            minute = int(hh_mm[1])
            spawn_time = PH_TZ.localize(datetime.combine(check_date.date(), time(hour=hour, minute=minute)))
            if spawn_time > now:  # Only future times
                next_spawn = spawn_time
                break

    return next_spawn

def get_time_remaining(respawn_time):
    now = datetime.now(PH_TZ)
    remaining = respawn_time - now
    if remaining.total_seconds() <= 0:
        return "🟢 **Spawned!**"
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m remaining"

# ------------------------- EVENTS -------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    check_respawns.start()

# ------------------------- COMMANDS -------------------------
COMMAND_CHANNEL_IDS = [
    1429295248592601108,
    1434140498314006548,
]
@bot.command(name="setkill")
async def set_kill(ctx, name: str, kill_time_str: str = None):
    """Set boss kill time manually (HH:MM). Adds default respawn hours"""
    if ctx.channel.id not in COMMAND_CHANNEL_IDS:
        return  # ignore commands from other channels

    data = load_data(ctx)
    name = name.lower()
    now = datetime.now(PH_TZ)

    # Parse kill time if provided
    if kill_time_str:
        try:
            kill_time = datetime.strptime(kill_time_str, "%H:%M").time()
            kill_datetime = PH_TZ.localize(datetime.combine(now.date(), kill_time))
            if kill_datetime > now:
                kill_datetime -= timedelta(days=1)
        except ValueError:
            await ctx.send("⚠️ Invalid time format. Use `!setkill <boss> <HH:MM>`")
            return
    else:
        kill_datetime = now

    # Determine respawn
    if name in BOSS_RESPAWN:
        respawn_hours = BOSS_RESPAWN[name]
        respawn_datetime = kill_datetime + timedelta(hours=respawn_hours)
        data[name] = {
            "boss": name.capitalize(),
            "type": "normal",
            "killed_at": kill_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "respawn_at": respawn_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "respawn_hours": respawn_hours,
            "announced": False,
            "warned": False
        }
        await ctx.send(
            f"🩸 **{name.capitalize()}** killed at `{kill_datetime.strftime('%H:%M')}`.\n"
            f"Will respawn at `{respawn_datetime.strftime('%H:%M')}` (+{respawn_hours}h)."
        )

    elif name in FIXED_SCHEDULE:
        days_hours = FIXED_SCHEDULE[name]["days_hours"]
        next_spawn = get_next_fixed_spawn(days_hours)
        data[name] = {
            "boss": name.capitalize(),
            "type": "fixed",
            "killed_at": kill_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "next_spawn": next_spawn.strftime("%Y-%m-%d %H:%M:%S") if next_spawn else None,
            "days_hours": days_hours,
            "announced": False,
            "warned": False
        }
        await ctx.send(
            f"📅 **{name.capitalize()}** follows fixed schedule: "
            f"{', '.join(days_hours.keys()).title()} ({', '.join(days_hours.values())})\n"
            f"Next spawn: `{next_spawn.strftime('%A %H:%M') if next_spawn else 'Not set'}`"
        )

    else:
        await ctx.send(f"⚠️ Unknown boss `{name}`.")

    save_data(data, ctx)


@bot.command(name="schedule")
async def boss_schedule(ctx):
    if ctx.channel.id not in COMMAND_CHANNEL_IDS:
        return
    data = load_data(ctx)
    now = datetime.now(PH_TZ)

    for name, info in FIXED_SCHEDULE.items():
        if name not in data:
            next_spawn = get_next_fixed_spawn(info["days_hours"])
            data[name] = {
                "boss": name.capitalize(),
                "type": "fixed",
                "next_spawn": next_spawn.strftime("%Y-%m-%d %H:%M:%S") if next_spawn else None,
                "days_hours": info["days_hours"],
                "announced": False
            }

    boss_list = []
    for name, info in data.items():
        if info["type"] == "normal":
            respawn_time = PH_TZ.localize(datetime.strptime(info["respawn_at"], "%Y-%m-%d %H:%M:%S"))
        else:
            respawn_time = PH_TZ.localize(datetime.strptime(info["next_spawn"], "%Y-%m-%d %H:%M:%S"))
        boss_list.append((respawn_time, info))

    if not boss_list:
        await ctx.send("No boss records found.")
        return  # ✅ FIXED

    boss_list.sort(key=lambda x: x[0])

    today = now.date()
    tomorrow = today + timedelta(days=1)

    output = []
    def format_day_header(dt):
        day_name = dt.strftime("%A")
        date_str = dt.strftime("%d/%m")
        if dt.date() == today:
            return f"**THIS DAY ({day_name}, {date_str})**"
        else:
            return f"**NEXT DAY ({day_name}, {date_str})**"

    day_bosses = {today: [], tomorrow: []}
    for spawn_time, info in boss_list:
        if spawn_time.date() in [today, tomorrow]:
            remaining = get_time_remaining(spawn_time)
            time_str = spawn_time.strftime("%I:%M %p").lstrip("0")
            day_bosses[spawn_time.date()].append(f"**{time_str}** | **{info['boss'].upper()}** ({remaining})")

    for day in [today, tomorrow]:
        if day_bosses[day]:
            output.append(format_day_header(datetime.combine(day, time())))
            output.extend(day_bosses[day])
            output.append("")

    await ctx.send("\n".join(output))


# ------------------------- AUTO SPAWN CHECK -------------------------
@tasks.loop(seconds=10)
async def check_respawns():

    for guild in bot.guilds:
        data = load_data(guild_id=guild.id)
        now = datetime.now(PH_TZ)
        updated = False

        # Find channel for this guild only
        guild_channels = [ch for ch in guild.channels if ch.id in COMMAND_CHANNEL_IDS]

        if not guild_channels:
            continue

        for name, info in data.items():
            if info["type"] == "normal":
                respawn_time = PH_TZ.localize(datetime.strptime(info["respawn_at"], "%Y-%m-%d %H:%M:%S"))
            else:
                respawn_time = PH_TZ.localize(datetime.strptime(info["next_spawn"], "%Y-%m-%d %H:%M:%S"))

            remaining_seconds = (respawn_time - now).total_seconds()

            # 10 min warning
            if 0 < remaining_seconds <= 600 and not info.get("warned"):
                for channel in guild_channels:
                    await channel.send(f"⏰ @here **{info['boss']}** respawning in 10 minutes!")
                info["warned"] = True
                updated = True

            # Respawned message
            elif remaining_seconds <= 0 and not info.get("announced"):
                for channel in guild_channels:
                    await channel.send(f"⚔️ @here **{info['boss']}** has respawned!")
                info["announced"] = True
                
                # ✅ If fixed schedule, compute next weekly spawn
                if info["type"] == "fixed":
                    next_spawn = get_next_fixed_spawn(info["days_hours"])
                    info["next_spawn"] = next_spawn.strftime("%Y-%m-%d %H:%M:%S") if next_spawn else None
                    info["announced"] = False
                    info["warned"] = False

                updated = True
        if updated:
            save_data(data, guild_id=guild.id)


# ------------------------- RUN BOT -------------------------
bot.run(TOKEN)


