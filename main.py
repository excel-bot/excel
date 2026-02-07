import discord
from discord.ext import commands, tasks
import json, os
from datetime import datetime, timedelta, time
import pytz
from dotenv import load_dotenv
from keep_alive import keep_alive

keep_alive()

# ================= CONFIG =================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

PH_TZ = pytz.timezone("Asia/Manila")
DATA_FOLDER = "data"

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# ================= NORMAL BOSSES =================
BOSS_RESPAWN = {
    "venatus": 10, "viorent": 10, "ego": 21, "livera": 24,
    "araneo": 24, "undomiel": 24, "ladydalia": 18,
    "general": 29, "amentis": 29, "baron": 32,
    "wannitas": 48, "metus": 48, "duplican": 48,
    "shuliar": 35, "gareth": 32, "titore": 37,
    "larba": 35, "catena": 35,
    "secreta": 62, "ordo": 62, "asta": 62, "supore": 62
}

# ================= FIXED BOSSES =================
FIXED_SCHEDULE = {
    "clemantis": {"monday": "11:30", "thursday": "19:00"},
    "saphirus": {"sunday": "17:00", "tuesday": "11:30"},
    "neutro": {"tuesday": "19:00", "thursday": "11:30"},
    "thymele": {"monday": "19:00", "wednesday": "11:30"},
    "milavy": {"saturday": "15:00"},
    "ringor": {"saturday": "17:00"},
    "roderick": {"friday": "19:00"},
    "auraq": {"friday": "22:00", "wednesday": "21:00"},
    "chaiflock": {"saturday": "22:00"},
    "benji": {"sunday": "21:00"},
    "tumier": {"sunday": "19:00"}
}

COMMAND_CHANNEL_IDS = [
    1429295248592601108,
    1434140498314006548,
    1453753393217667196
]

# ================= STORAGE =================
def file_path(gid, cid):
    return f"{DATA_FOLDER}/boss_data_{gid}_{cid}.json"

def load_data(guild_id, channel_id):
    f = file_path(guild_id, channel_id)
    if not os.path.exists(f):
        return {}
    try:
        with open(f, "r") as x:
            t = x.read().strip()
            return json.loads(t) if t else {}
    except:
        return {}

def save_data(guild_id, channel_id, data):
    f = file_path(guild_id, channel_id)
    with open(f, "w") as x:
        json.dump(data, x, indent=4)

# ================= TIME HELPERS =================
def next_fixed_spawn(schedule):
    now = datetime.now(PH_TZ)

    for i in range(8):  # 8-day safety window
        day = now + timedelta(days=i)
        d = day.strftime("%A").lower()

        if d in schedule:
            h, m = map(int, schedule[d].split(":"))
            dt = PH_TZ.localize(datetime.combine(day.date(), time(h, m)))

            if dt > now:
                return dt

    return None

# ================= EVENTS =================
@bot.event
async def on_ready():
    print("✅ Bot running")
    if not check.is_running():
        check.start()

# ================= SETKILL =================
@bot.command()
async def setkill(ctx, boss: str, time_str: str = None):
    if ctx.channel.id not in COMMAND_CHANNEL_IDS:
        return

    boss = boss.lower()
    data = load_data(ctx.guild.id, ctx.channel.id)
    now = datetime.now(PH_TZ)

    if time_str:
        try:
            hh, mm = map(int, time_str.split(":"))
            kill_time = PH_TZ.localize(datetime.combine(now.date(), time(hh, mm)))
            if kill_time > now:
                kill_time -= timedelta(days=1)
        except:
            return await ctx.send("❌ Format: `!setkill boss HH:MM`")
    else:
        kill_time = now

    # NORMAL
    if boss in BOSS_RESPAWN:
        respawn = kill_time + timedelta(hours=BOSS_RESPAWN[boss])
        data[boss] = {
            "type": "normal",
            "respawn": respawn.strftime("%Y-%m-%d %H:%M:%S"),
            "warn": False,
            "announce": False,
            "locked": False
        }
        save_data(ctx.guild.id, ctx.channel.id, data)

        embed = discord.Embed(
            title=f"🩸 {boss.upper()} Scheduled",
            description=f"Respawn at **{respawn.strftime('%A %I:%M %p')}**",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed)

    # FIXED
    if boss in FIXED_SCHEDULE:
        nxt = next_fixed_spawn(FIXED_SCHEDULE[boss])
        if not nxt:
            return await ctx.send("❌ Could not determine next spawn.")

        data[boss] = {
            "type": "fixed",
            "next": nxt.strftime("%Y-%m-%d %H:%M:%S"),
            "days": FIXED_SCHEDULE[boss],
            "warn": False,
            "announce": False,
            "locked": False
        }

        save_data(ctx.guild.id, ctx.channel.id, data)

        embed = discord.Embed(
            title=f"📅 {boss.upper()} Scheduled",
            description=f"Next spawn: **{nxt.strftime('%A %I:%M %p')}**",
            color=discord.Color.blue()
        )
        return await ctx.send(embed=embed)

    await ctx.send("❌ Unknown boss.")

# ================= SCHEDULE =================
@bot.command()
async def schedule(ctx):
    if ctx.channel.id not in COMMAND_CHANNEL_IDS:
        return

    data = load_data(ctx.guild.id, ctx.channel.id)
    now = datetime.now(PH_TZ)

    events = []
    for b, i in data.items():
        try:
            key = "respawn" if i["type"] == "normal" else "next"
            t = PH_TZ.localize(datetime.strptime(i[key], "%Y-%m-%d %H:%M:%S"))
            events.append((t, b))
        except:
            continue

    if not events:
        return await ctx.send("⚠️ No records yet.")

    events.sort(key=lambda x: x[0])

    embed = discord.Embed(
        title="📅 Boss Schedule (Today & Tomorrow)",
        color=discord.Color.gold()
    )

    today = now.date()
    tomorrow = today + timedelta(days=1)

    for label, day in [("TODAY", today), ("TOMORROW", tomorrow)]:
        lines = []
        for t, b in events:
            if t.date() == day:
                ts = int(t.timestamp())
                lines.append(f"📌 <t:{ts}:t> — **{b.upper()}**")

        if lines:
            embed.add_field(
                name=label,
                value="\n".join(lines),
                inline=False
            )

    await ctx.send(embed=embed)

# ================= WEEK =================
@bot.command()
async def week(ctx):
    if ctx.channel.id not in COMMAND_CHANNEL_IDS:
        return

    data = load_data(ctx.guild.id, ctx.channel.id)
    now = datetime.now(PH_TZ)

    events = []
    for b, i in data.items():
        try:
            key = "respawn" if i["type"] == "normal" else "next"
            t = PH_TZ.localize(datetime.strptime(i[key], "%Y-%m-%d %H:%M:%S"))
            if t >= now:
                events.append((t, b))
        except:
            continue

    if not events:
        return await ctx.send("⚠️ No upcoming spawns.")

    events.sort(key=lambda x: x[0])

    embed = discord.Embed(
        title="📅 Boss Schedule (Next 7 Days)",
        color=discord.Color.green()
    )

    for i in range(7):
        day = (now + timedelta(days=i)).date()
        label = day.strftime("%A").upper()
        lines = []

        for t, b in events:
            if t.date() == day:
                ts = int(t.timestamp())
                lines.append(f"📌 <t:{ts}:t> — **{b.upper()}**")

        if lines:
            embed.add_field(
                name=label,
                value="\n".join(lines),
                inline=False
            )

    await ctx.send(embed=embed)

# ================= AUTO CHECK =================
@tasks.loop(seconds=10)
async def check():
    now = datetime.now(PH_TZ)

    for g in bot.guilds:
        for c in g.text_channels:
            if c.id not in COMMAND_CHANNEL_IDS:
                continue

            data = load_data(g.id, c.id)
            changed = False

            for b, i in list(data.items()):
                try:
                    key = "respawn" if i["type"] == "normal" else "next"
                    t = PH_TZ.localize(datetime.strptime(i[key], "%Y-%m-%d %H:%M:%S"))
                except:
                    continue

                sec = (t - now).total_seconds()

                # 10 MIN WARNING
                if 570 <= sec <= 630 and not i["warn"]:
                    ts = int(t.timestamp())
                    await c.send(
                        f"⏰ @here **{b.upper()}** will spawn in 10 minutes!\n"
                        f"Spawn Time: <t:{ts}:F>"
                    )
                    i["warn"] = True
                    changed = True

                if sec > 630:
                    i["warn"] = False

                # SPAWN
                if sec <= 0 and not i["announce"] and not i.get("locked", False):
                    if sec >= -120:
                        await c.send(f"⚔️ @here **{b.upper()} SPAWNED!**")

                    i["announce"] = True
                    i["locked"] = True
                    changed = True

                    if i["type"] == "fixed":
                        nxt = next_fixed_spawn(i["days"])
                        if nxt:
                            i["next"] = nxt.strftime("%Y-%m-%d %H:%M:%S")
                            i["warn"] = False
                            i["announce"] = False
                            i["locked"] = False

                if i.get("locked") and sec < -3600:
                    i["locked"] = False
                    changed = True

            if changed:
                save_data(g.id, c.id, data)

# ================= RUN =================
bot.run(TOKEN)
