import discord
from discord.ext import commands, tasks
import sqlite3, json, os
from datetime import datetime, timedelta, time
import pytz
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

PH_TZ = pytz.timezone("Asia/Manila")

# ✅ ADMIN ONLY (replace with your Discord ID)
ADMIN_IDS = [703982684191326269]

# ================= SQLITE =================
conn = sqlite3.connect("boss.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bosses (
    guild_id INTEGER,
    channel_id INTEGER,
    name TEXT,
    data TEXT,
    PRIMARY KEY (guild_id, channel_id, name)
)
""")
conn.commit()

def save_boss(gid, cid, name, data):
    cursor.execute("REPLACE INTO bosses VALUES (?, ?, ?, ?)",
                   (gid, cid, name, json.dumps(data)))
    conn.commit()

def load_bosses(gid, cid):
    cursor.execute("SELECT name, data FROM bosses WHERE guild_id=? AND channel_id=?",
                   (gid, cid))
    return {n: json.loads(d) for n, d in cursor.fetchall()}

def delete_boss(gid, cid, name):
    cursor.execute("DELETE FROM bosses WHERE guild_id=? AND channel_id=? AND name=?",
                   (gid, cid, name))
    conn.commit()

# ================= TIME =================
def next_fixed_spawn(schedule):
    now = datetime.now(PH_TZ)

    for i in range(8):  # fix weekly bug
        day = now + timedelta(days=i)
        d = day.strftime("%A").lower()

        if d in schedule:
            h, m = map(int, schedule[d].split(":"))
            dt = PH_TZ.localize(datetime.combine(day.date(), time(h, m)))

            if dt > now:
                return dt
    return None

# ================= EMBED =================
def make_embed(title, desc, color=0x00ffcc):
    return discord.Embed(title=title, description=desc, color=color)

# ================= EVENTS =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not check.is_running():
        check.start()

# ================= ADMIN COMMANDS =================
@bot.command()
async def addboss(ctx, name: str, btype: str, *args):
    if ctx.author.id not in ADMIN_IDS:
        return

    name = name.lower()
    btype = btype.lower()

    data = load_bosses(ctx.guild.id, ctx.channel.id)

    if btype == "normal":
        hours = int(args[0])
        data[name] = {
            "type": "normal",
            "respawn_hours": hours,
            "respawn": "",
            "warn": False,
            "announce": False,
            "locked": False
        }

    elif btype == "fixed":
        # example: monday=11:30 thursday=19:00
        schedule = {}
        for pair in args:
            d, t = pair.split("=")
            schedule[d.lower()] = t

        data[name] = {
            "type": "fixed",
            "days": schedule,
            "next": "",
            "warn": False,
            "announce": False,
            "locked": False
        }

    else:
        return await ctx.send("❌ Type must be normal/fixed")

    save_boss(ctx.guild.id, ctx.channel.id, name, data[name])

    await ctx.send(embed=make_embed("✅ Boss Added", f"**{name.upper()}** added."))

@bot.command()
async def removeboss(ctx, name: str):
    if ctx.author.id not in ADMIN_IDS:
        return

    delete_boss(ctx.guild.id, ctx.channel.id, name.lower())
    await ctx.send(embed=make_embed("🗑 Removed", f"{name.upper()} deleted"))

# ================= SETKILL =================
@bot.command()
async def setkill(ctx, name: str, time_str: str = None):
    data = load_bosses(ctx.guild.id, ctx.channel.id)

    name = name.lower()
    if name not in data:
        return await ctx.send("❌ Boss not found")

    now = datetime.now(PH_TZ)

    if time_str:
        hh, mm = map(int, time_str.split(":"))
        kill = PH_TZ.localize(datetime.combine(now.date(), time(hh, mm)))
        if kill > now:
            kill -= timedelta(days=1)
    else:
        kill = now

    boss = data[name]

    if boss["type"] == "normal":
        respawn = kill + timedelta(hours=boss["respawn_hours"])
        boss["respawn"] = respawn.strftime("%Y-%m-%d %H:%M:%S")

    else:
        nxt = next_fixed_spawn(boss["days"])
        if not nxt:
            return await ctx.send("❌ No next spawn")
        boss["next"] = nxt.strftime("%Y-%m-%d %H:%M:%S")

    boss["warn"] = False
    boss["announce"] = False
    boss["locked"] = False

    save_boss(ctx.guild.id, ctx.channel.id, name, boss)

    await ctx.send(embed=make_embed("🩸 Set Kill", f"{name.upper()} updated"))

# ================= SCHEDULE =================
@bot.command()
async def schedule(ctx):
    data = load_bosses(ctx.guild.id, ctx.channel.id)
    now = datetime.now(PH_TZ)

    events = []

    for b, i in data.items():
        try:
            key = "respawn" if i["type"] == "normal" else "next"
            if not i.get(key):
                continue
            t = PH_TZ.localize(datetime.strptime(i[key], "%Y-%m-%d %H:%M:%S"))
            events.append((t, b))
        except:
            continue

    if not events:
        return await ctx.send("⚠️ No data")

    events.sort()

    today = now.date()
    tomorrow = today + timedelta(days=1)

    desc = ""

    for label, day in [("TODAY", today), ("TOMORROW", tomorrow)]:
        section = f"**{label}**\n"
        for t, b in events:
            if t.date() == day:
                ts = int(t.timestamp())
                section += f"📌 <t:{ts}:t> | **{b.upper()}**\n"
        desc += section + "\n"

    await ctx.send(embed=make_embed("📅 Schedule", desc))

# ================= WEEK =================
@bot.command()
async def week(ctx):
    data = load_bosses(ctx.guild.id, ctx.channel.id)
    now = datetime.now(PH_TZ)

    events = []

    for b, i in data.items():
        try:
            key = "respawn" if i["type"] == "normal" else "next"
            if not i.get(key):
                continue
            t = PH_TZ.localize(datetime.strptime(i[key], "%Y-%m-%d %H:%M:%S"))
            if t >= now:
                events.append((t, b))
        except:
            continue

    if not events:
        return await ctx.send("⚠️ No upcoming")

    events.sort()

    desc = ""
    for i in range(7):
        day = (now + timedelta(days=i)).date()
        label = day.strftime("%A").upper()

        section = f"**{label}**\n"
        for t, b in events:
            if t.date() == day:
                ts = int(t.timestamp())
                section += f"📌 <t:{ts}:t> | **{b.upper()}**\n"

        if section.strip() != f"**{label}**":
            desc += section + "\n"

    await ctx.send(embed=make_embed("📅 Weekly Schedule", desc))

# ================= AUTO CHECK =================
@tasks.loop(seconds=10)
async def check():
    now = datetime.now(PH_TZ)

    for g in bot.guilds:
        for c in g.text_channels:

            data = load_bosses(g.id, c.id)
            if not data:
                continue

            changed = False

            for b, i in data.items():
                try:
                    key = "respawn" if i["type"] == "normal" else "next"
                    if not i.get(key):
                        continue

                    t = PH_TZ.localize(datetime.strptime(i[key], "%Y-%m-%d %H:%M:%S"))
                except:
                    continue

                sec = (t - now).total_seconds()

                # 10 min warning
                if 570 <= sec <= 630 and not i["warn"]:
                    await c.send(f"⏰ @here **{b.upper()}** in 10 minutes!")
                    i["warn"] = True
                    changed = True

                if sec > 630:
                    i["warn"] = False

                # spawn
                if sec <= 0 and not i["announce"] and not i["locked"]:
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
                for name, d in data.items():
                    save_boss(g.id, c.id, name, d)

# ================= RUN =================
bot.run(TOKEN)
