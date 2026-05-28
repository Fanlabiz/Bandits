import re
import streamlit as st
from datetime import datetime, timedelta

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="⚔️ Planificateur de Bandits",
    page_icon="⚔️",
    layout="centered",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=MedievalSharp&family=Crimson+Pro:wght@400;600&family=Source+Code+Pro:wght@400;600&display=swap');

html, body, [class*="css"] {
    background-color: #0e0c0a;
    color: #e8dcc8;
}

.stApp {
    background: radial-gradient(ellipse at 20% 10%, #1a120a 0%, #0e0c0a 60%);
}

h1, h2, h3 {
    font-family: 'Crimson Pro', serif;
    color: #d4a84b;
    letter-spacing: 0.04em;
}

.title-block {
    text-align: center;
    padding: 2rem 0 1rem;
    border-bottom: 1px solid #3a2e1e;
    margin-bottom: 2rem;
}

.title-block h1 {
    font-size: 2.8rem;
    margin-bottom: 0.2rem;
    text-shadow: 0 0 30px #d4a84b44;
}

.title-block p {
    font-family: 'Crimson Pro', serif;
    color: #8a7a5e;
    font-size: 1.1rem;
}

.stTextArea textarea {
    background-color: #1a1510 !important;
    color: #c8b88a !important;
    border: 1px solid #3a2e1e !important;
    font-family: 'Source Code Pro', monospace !important;
    font-size: 0.85rem !important;
    border-radius: 6px !important;
}

.stTextArea textarea:focus {
    border-color: #d4a84b !important;
    box-shadow: 0 0 0 1px #d4a84b44 !important;
}

.stButton > button {
    background: linear-gradient(135deg, #8b3a00, #c45a10) !important;
    color: #f5e8d0 !important;
    border: none !important;
    font-family: 'Crimson Pro', serif !important;
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    padding: 0.6rem 2.5rem !important;
    border-radius: 4px !important;
    letter-spacing: 0.08em !important;
    width: 100% !important;
    transition: all 0.2s !important;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #a04510, #d46a20) !important;
    box-shadow: 0 0 20px #c45a1044 !important;
}

.bandit-card {
    background: linear-gradient(135deg, #1a1208 0%, #130f08 100%);
    border: 1px solid #3a2e1e;
    border-left: 4px solid #d4a84b;
    border-radius: 6px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1rem;
    font-family: 'Crimson Pro', serif;
}

.bandit-card.impossible {
    border-left-color: #8b3a00;
}

.bandit-stars {
    font-size: 1.4rem;
    margin-bottom: 0.4rem;
}

.bandit-label {
    color: #8a7a5e;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

.bandit-time {
    color: #d4a84b;
    font-size: 1.5rem;
    font-weight: 600;
}

.bandit-end {
    color: #8a7a5e;
    font-size: 1rem;
}

.bandit-appear {
    color: #c8b88a;
    font-size: 1rem;
}

.impossible-label {
    color: #c04040;
    font-size: 1.1rem;
    font-weight: 600;
}

.raw-output {
    background: #0a0805;
    border: 1px solid #2a2010;
    border-radius: 6px;
    padding: 1.5rem;
    font-family: 'Source Code Pro', monospace;
    font-size: 0.85rem;
    color: #c8b88a;
    white-space: pre-wrap;
    margin-top: 1rem;
}

.section-title {
    font-family: 'Crimson Pro', serif;
    color: #8a7a5e;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 1rem;
    margin-top: 2rem;
    border-bottom: 1px solid #2a2010;
    padding-bottom: 0.4rem;
}

.error-box {
    background: #1a0808;
    border: 1px solid #6a2020;
    border-radius: 6px;
    padding: 1rem 1.5rem;
    color: #c04040;
    font-family: 'Crimson Pro', serif;
}

.count-badge {
    display: inline-block;
    background: #d4a84b22;
    border: 1px solid #d4a84b55;
    color: #d4a84b;
    font-family: 'Source Code Pro', monospace;
    font-size: 0.8rem;
    padding: 0.15rem 0.6rem;
    border-radius: 20px;
    margin-left: 0.5rem;
    vertical-align: middle;
}
</style>
""", unsafe_allow_html=True)

# ─── Logic (reprise du bot Discord) ─────────────────────────────────────────

def get_ideal_windows(day_of_week):
    if day_of_week < 5:
        return [(7, 9), (12, 13), (18, 22)]
    else:
        return [(9, 23)]

def find_attack_time(bandit_appearance, busy_until):
    bandit_end = bandit_appearance + timedelta(hours=8)
    candidates = []

    for delta_days in range(3):
        day = bandit_appearance.date() + timedelta(days=delta_days)
        weekday = day.weekday()
        windows = get_ideal_windows(weekday)
        for (start_h, end_h) in windows:
            candidates.append(datetime(day.year, day.month, day.day, start_h, 0, 0))
        candidates.append(datetime(day.year, day.month, day.day, 6, 0, 0))

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
            break

        if not in_window and best_fallback is None:
            best_fallback = candidate

    return best_ideal if best_ideal else best_fallback

def parse_bandits(text):
    pattern = r"Incident (⭐+) va apparaître le (\d{1,2}) (\w+) (\d{4}) à (\d{2}:\d{2}:\d{2})"
    mois_fr = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }
    bandits = []
    for match in re.finditer(pattern, text):
        stars = match.group(1)
        day = int(match.group(2))
        month = mois_fr.get(match.group(3).lower(), 1)
        year = int(match.group(4))
        h, m, s = match.group(5).split(":")
        appearance = datetime(year, month, day, int(h), int(m), int(s))
        bandits.append({"stars": stars, "appearance": appearance})
    return bandits

def calculate_attacks(bandits):
    busy_until = datetime.min
    results = []
    for bandit in sorted(bandits, key=lambda x: x["appearance"]):
        attack_time = find_attack_time(bandit["appearance"], busy_until)
        if attack_time:
            end_time = attack_time + timedelta(hours=4)
            busy_until = end_time
            results.append({**bandit, "attack": attack_time, "end": end_time})
        else:
            results.append({**bandit, "attack": None, "end": None})
    return results

def format_results_text(results):
    jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    lines = ["Hello Beta,", "", "**⚔️ Plan d'attaque des bandits :**\n"]
    for r in results:
        jour = jours_fr[r["appearance"].weekday()]
        appear_str = r["appearance"].strftime("%d/%m à %H:%M")
        if r["attack"]:
            attack_jour = jours_fr[r["attack"].weekday()]
            lines.append(
                f"{r['stars']} — Apparition : {jour} {appear_str}\n"
                f"   ➡️ Attaquer le {attack_jour} à **{r['attack'].strftime('%H:%M')}**\n"
            )
        else:
            lines.append(
                f"{r['stars']} — Apparition : {jour} {appear_str}\n"
                f"   ❌ Aucune heure d'attaque possible\n"
            )
    return "\n".join(lines)

# ─── UI ─────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="title-block">
    <h1>⚔️ Planificateur de Bandits</h1>
    <p>Collez le message Beta Hunter Fr pour générer votre plan d'attaque</p>
</div>
""", unsafe_allow_html=True)

# Input : texte direct ou fichier
tab1, tab2 = st.tabs(["📋 Coller le texte", "📁 Charger un fichier"])

raw_text = ""

with tab1:
    raw_text_input = st.text_area(
        "Message Beta Hunter Fr",
        height=220,
        placeholder="Incident ⭐⭐⭐ va apparaître le 6 avril 2026 à 14:30:00\nIncident ⭐⭐ va apparaître le 7 avril 2026 à 08:00:00\n...",
        label_visibility="collapsed",
    )
    if raw_text_input.strip():
        raw_text = raw_text_input

with tab2:
    uploaded = st.file_uploader("Fichier texte", type=["txt"], label_visibility="collapsed")
    if uploaded:
        raw_text = uploaded.read().decode("utf-8")
        st.markdown(f'<div class="section-title">Contenu du fichier</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="raw-output">{raw_text}</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
go = st.button("⚔️ Calculer le plan d'attaque")

if go:
    if not raw_text.strip():
        st.markdown('<div class="error-box">⚠️ Aucun texte fourni. Collez le message ou chargez un fichier.</div>', unsafe_allow_html=True)
    else:
        bandits = parse_bandits(raw_text)
        if not bandits:
            st.markdown('<div class="error-box">❌ Aucun incident trouvé dans le texte.<br>Vérifiez le format : <code>Incident ⭐⭐ va apparaître le 6 avril 2026 à 14:30:00</code></div>', unsafe_allow_html=True)
        else:
            results = calculate_attacks(bandits)
            jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

            n = len(results)
            n_ok = sum(1 for r in results if r["attack"])
            st.markdown(
                f'<div class="section-title">Plan d\'attaque '
                f'<span class="count-badge">{n_ok}/{n} planifiés</span></div>',
                unsafe_allow_html=True
            )

            for r in results:
                jour = jours_fr[r["appearance"].weekday()]
                appear_str = r["appearance"].strftime("%d/%m à %H:%M")

                if r["attack"]:
                    attack_jour = jours_fr[r["attack"].weekday()]
                    st.markdown(f"""
                    <div class="bandit-card">
                        <div class="bandit-stars">{r['stars']}</div>
                        <div class="bandit-label">Apparition</div>
                        <div class="bandit-appear">{jour} {appear_str}</div>
                        <br>
                        <div class="bandit-label">Attaquer</div>
                        <div class="bandit-time">{attack_jour} à {r['attack'].strftime('%H:%M')}</div>
                        <div class="bandit-end">fin à {r['end'].strftime('%H:%M')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="bandit-card impossible">
                        <div class="bandit-stars">{r['stars']}</div>
                        <div class="bandit-label">Apparition</div>
                        <div class="bandit-appear">{jour} {appear_str}</div>
                        <br>
                        <div class="impossible-label">❌ Aucune heure d'attaque possible</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Texte copie-colle (même format que le bot Discord)
            st.markdown('<div class="section-title">Message à copier (format Discord)</div>', unsafe_allow_html=True)
            discord_text = format_results_text(results)
            # Retire le markdown bold pour l'affichage brut
            plain = discord_text.replace("**", "")
            st.markdown(f'<div class="raw-output">{plain}</div>', unsafe_allow_html=True)

            # Bouton copier via JavaScript
            escaped = plain.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
            st.components.v1.html(f"""
                <button onclick="navigator.clipboard.writeText(`{escaped}`).then(() => {{
                    this.innerText = '✅ Copié !';
                    setTimeout(() => this.innerText = '📋 Copier le message', 2000);
                }})" style="
                    background: linear-gradient(135deg, #8b3a00, #c45a10);
                    color: #f5e8d0;
                    border: none;
                    font-family: 'Crimson Pro', serif;
                    font-size: 1.1rem;
                    font-weight: 600;
                    padding: 0.6rem 2.5rem;
                    border-radius: 4px;
                    letter-spacing: 0.08em;
                    width: 100%;
                    cursor: pointer;
                    transition: all 0.2s;
                " onmouseover="this.style.background='linear-gradient(135deg, #a04510, #d46a20)'"
                   onmouseout="this.style.background='linear-gradient(135deg, #8b3a00, #c45a10)'">
                    📋 Copier le message
                </button>
            """, height=60)
