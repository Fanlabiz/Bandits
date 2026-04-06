import os
import re
import discord
from datetime import datetime, timedelta
from discord.ext import commands

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

CANAL_ID = 1401991626976530556
MEMBRE_ID = 628941719576117249

def get_ideal_windows(day_of_week):
    """Retourne les fenêtres idéales selon le jour (0=lundi, 6=dimanche)"""
    if day_of_week < 5:  # Lundi à vendredi
        return [(8, 9), (12, 13), (18, 22)]
    else:  # Samedi et dimanche
        return [(9, 23)]

def find_attack_time(bandit_appearance, busy_until):
    bandit_end = bandit_appearance + timedelta(hours=8)
    
    candidates = []
    
    for delta_days in range(3):
        day = bandit_appearance.date() + timedelta(days=delta_days)
        weekday = day.weekday()
        windows = get_ideal_windows(weekday)
        
        for (start_h, end_h) in windows:
            candidate = datetime(day.year, day.month, day.day, start_h, 0, 0)
            candidates.append(candidate)
        
        # Ajouter 06:00 comme candidat de secours (hors fenêtre idéale mais autorisé)
        candidate_6h = datetime(day.year, day.month, day.day, 6, 0, 0)
        candidates.append(candidate_6h)
    
    candidates.append(bandit_appearance)
    if busy_until > bandit_appearance:
        candidates.append(busy_until)
    
    candidates.sort()
    
    best_ideal = None
    best_fallback = None
    
    for candidate in candidates:
        if candidate < bandit_appearance:
            continue
        if candidate < busy_until:
            continue
        if candidate >= bandit_end:
            continue
        if candidate.hour >= 23 or candidate.hour < 6:
            continue
        
        windows = get_ideal_windows(candidate.weekday())
        in_window = any(start_h <= candidate.hour < end_h for start_h, end_h in windows)
        
        if in_window and best_ideal is None:
            best_ideal = candidate
            break  # On prend la première fenêtre idéale trouvée
        
        if not in_window and best_fallback is None:
            best_fallback = candidate
    
    # Priorité à la fenêtre idéale, sinon fallback (ex: 06:00)
    return best_ideal if best_ideal else best_fallback


def parse_bandits(message_content):
    """Extrait les bandits du message Discord"""
    pattern = r"Incident (⭐+) va apparaître le (\d{1,2}) (\w+) (\d{4}) à (\d{2}:\d{2}:\d{2})"
    
    mois_fr = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }
    
    bandits = []
    for match in re.finditer(pattern, message_content):
        stars = match.group(1)
        day = int(match.group(2))
        month = mois_fr.get(match.group(3).lower(), 1)
        year = int(match.group(4))
        time_parts = match.group(5).split(":")
        
        appearance = datetime(year, month, day, int(time_parts[0]), int(time_parts[1]), int(time_parts[2]))
        bandits.append({"stars": stars, "appearance": appearance})
    
    return bandits

def calculate_attacks(bandits):
    """Calcule les heures d'attaque optimales pour chaque bandit"""
    busy_until = datetime.min
    results = []
    
    # On attaque dans l'ordre d'apparition
    bandits_sorted = sorted(bandits, key=lambda x: x["appearance"])
    
    for bandit in bandits_sorted:
        attack_time = find_attack_time(bandit["appearance"], busy_until)
        
        if attack_time:
            end_time = attack_time + timedelta(hours=4)
            busy_until = end_time
            results.append({
                "stars": bandit["stars"],
                "appearance": bandit["appearance"],
                "attack": attack_time,
                "end": end_time
            })
        else:
            results.append({
                "stars": bandit["stars"],
                "appearance": bandit["appearance"],
                "attack": None,
                "end": None
            })
    
    return results

def format_results(results):
    """Formate le message de réponse"""
    jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    
    lines = ["**⚔️ Plan d'attaque des bandits :**\n"]
    
    for r in results:
        appearance_str = r["appearance"].strftime("%d/%m à %H:%M")
        jour = jours_fr[r["appearance"].weekday()]
        
        if r["attack"]:
            attack_str = r["attack"].strftime("%H:%M")
            end_str = r["end"].strftime("%H:%M")
            attack_jour = jours_fr[r["attack"].weekday()]
            lines.append(
                f"{r['stars']} — Apparition : {jour} {appearance_str}\n"
                f"   ➡️ Attaquer le {attack_jour} à **{attack_str}** (fin à {end_str})\n"
            )
        else:
            lines.append(
                f"{r['stars']} — Apparition : {jour} {appearance_str}\n"
                f"   ❌ Aucune heure d'attaque possible\n"
            )
    
    return "\n".join(lines)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id == CANAL_ID and message.author.id == MEMBRE_ID:
        if "Beta Hunter Fr" in message.content and "Incident" in message.content:
            bandits = parse_bandits(message.content)
            if bandits:
                results = calculate_attacks(bandits)
                response = format_results(results)
                await message.channel.send(response)

    await bot.process_commands(message)

bot.run(os.environ["DISCORD_TOKEN"])

