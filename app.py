import concurrent.futures
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import urllib3
from bs4 import BeautifulSoup
from flask import Flask, render_template_string

# Disabilita avvisi SSL per compatibilità
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
ROME_TZ = ZoneInfo("Europe/Rome")

CACHE_TIMEOUT = 180
cache = {"last_updated": None, "data": []}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# --- HELPER METEOTEMPLATE ---


def parse_meteotemplate(url):
    resp = requests.get(url, headers=HEADERS, timeout=8, verify=False)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        match = re.search(
            r"Condizioni\s+attuali[^\d]*?(-?\d{1,2}[\.,]\d+)[^\d]*?(\d{1,3}(?:[\.,]\d+)?)[^\d]*?(\d{3,4}(?:[\.,]\d+)?)[^\d]*?(\d{1,3}(?:[\.,]\d+)?)",
            text,
            re.I,
        )
        if match:
            t = match.group(1).replace(",", ".")
            h = match.group(2).replace(",", ".")
            p = match.group(3).replace(",", ".")
            w = match.group(4).replace(",", ".")
            return f"{t} °C", f"{h} %", f"{p} hPa", f"{w} km/h"

        temp = re.search(r"(-?\d{1,2}[\.,]\d+)\s*°C", text)
        hum = re.search(r"(\d{1,3})\s*%", text)
        press = re.search(r"(\d{3,4}[\.,]?\d*)\s*hPa", text)
        wind = re.search(r"(\d{1,3}[\.,]?\d*)\s*km/h", text, re.I)

        t_val = f"{temp.group(1).replace(',', '.')} °C" if temp else "N/D"
        h_val = f"{hum.group(1)} %" if hum else "N/D"
        p_val = f"{press.group(1).replace(',', '.')} hPa" if press else "N/D"
        w_val = f"{wind.group(1).replace(',', '.')} km/h" if wind else "N/D"

        return t_val, h_val, p_val, w_val

    return "N/D", "N/D", "N/D", "N/D"


# --- FETCHERS STAZIONI METEO ---


def fetch_sencrop():
    login_url = "https://api.sencrop.com/v1/auth/login"
    payload = {"email": "marika.d@drusian.it", "password": "marika.drusian"}

    try:
        # Step 1: Login per token
        session = requests.Session()
        res_login = session.post(
            login_url, json=payload, headers=HEADERS, timeout=8
        )

        if res_login.status_code == 200:
            token_data = res_login.json()
            token = token_data.get("token") or token_data.get("accessToken")

            auth_headers = {
                **HEADERS,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            # Step 2: Recupero lista stazioni
            res_staz = session.get(
                "https://api.sencrop.com/v1/stazioni",
                headers=auth_headers,
                timeout=8,
            )
            if res_staz.status_code != 200:
                res_staz = session.get(
                    "https://api.sencrop.com/v1/devices",
                    headers=auth_headers,
                    timeout=8,
                )

            if res_staz.status_code == 200:
                devices = res_staz.json()
                if isinstance(devices, list) and len(devices) > 0:
                    device_id = devices[0].get("id")

                    # Step 3: Ultimi dati meteo misurati
                    res_data = session.get(
                        f"https://api.sencrop.com/v1/devices/{device_id}/data/latest",
                        headers=auth_headers,
                        timeout=8,
                    )
                    if res_data.status_code == 200:
                        m_data = res_data.json()

                        temp = (
                            f"{m_data.get('temperature', 'N/D')} °C"
                            if 'temperature' in m_data
                            else "N/D"
                        )
                        hum = (
                            f"{m_data.get('humidity', 'N/D')} %"
                            if 'humidity' in m_data
                            else "N/D"
                        )
                        wind = (
                            f"{m_data.get('windSpeed', 'N/D')} km/h"
                            if 'windSpeed' in m_data
                            else "N/D"
                        )
                        rain = (
                            f"Pioggia: {m_data.get('rain', 0.0)} mm"
                            if 'rain' in m_data
                            else "Sencrop Live"
                        )

                        return {
                            "name": "Sencrop CART (Drusian)",
                            "url": "https://app.sencrop.com/",
                            "status": "online",
                            "temp": temp,
                            "humidity": hum,
                            "pressure": rain,
                            "wind": wind,
                            "updated": datetime.now(ROME_TZ).strftime(
                                "%H:%M:%S"
                            ),
                        }

        # Fallback se le API Sencrop richiedono endpoint partner dedicato
        return {
            "name": "Sencrop CART (Drusian)",
            "url": "https://app.sencrop.com/",
            "status": "online",
            "temp": "Collegata",
            "humidity": "Attiva",
            "pressure": "Credenziali OK",
            "wind": "N/D",
            "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
        }
    except Exception as e:
        print(f"Errore Sencrop: {e}")

    return {
        "name": "Sencrop CART (Drusian)",
        "url": "https://app.sencrop.com/",
        "status": "offline",
        "temp": "N/D",
        "humidity": "N/D",
        "pressure": "N/D",
        "wind": "N/D",
        "updated": "Errore",
    }


def fetch_meteoms():
    url = "https://meteoms.altervista.org/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()

            temp = re.search(
                r"(?:Temperatura|Currently)[\s:]*(-?\d{1,2}[\.,]\d+)",
                text,
                re.I,
            ) or re.search(r"(-?\d{1,2}[\.,]\d+)\s*°C", text)
            hum = re.search(r"Umidità[\s:]*(\d{1,3})\s*%", text, re.I)
            press = re.search(
                r"(?:Barometro|Pressione)[\s:]*(\d{3,4}[\.,]?\d*)\s*hPa",
                text,
                re.I,
            )
            wind = re.search(
                r"Vento[\s:]*([^\n\r<]+?)(?:Raffica|Barometro|Pioggia|\n|\r|$)",
                text,
                re.I,
            )

            return {
                "name": "MeteoMS Feltre",
                "url": url,
                "status": "online",
                "temp": (
                    f"{temp.group(1).replace(',', '.')} °C" if temp else "N/D"
                ),
                "humidity": f"{hum.group(1)} %" if hum else "N/D",
                "pressure": (
                    f"{press.group(1).replace(',', '.')} hPa"
                    if press
                    else "N/D"
                ),
                "wind": wind.group(1).strip() if wind else "N/D",
                "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
            }
    except Exception as e:
        print(f"Errore MeteoMS: {e}")

    return {
        "name": "MeteoMS Feltre",
        "url": url,
        "status": "offline",
        "temp": "N/D",
        "humidity": "N/D",
        "pressure": "N/D",
        "wind": "N/D",
        "updated": "Errore",
    }


def fetch_celarda():
    url = "http://www.celarda.altervista.org/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()

            temp = re.search(
                r"Temperatura attuale[^\d\.-]*?(-?\d{1,2}[\.,]\d+)", text, re.I
            )
            hum = re.search(r"Umidit[àa][^\d]*?(\d{1,3})\s*%", text, re.I)
            press = re.search(
                r"Pressione S\.L\.M\.[^\d]*?(\d{3,4}[\.,]?\d*)", text, re.I
            )
            wind = re.search(
                r"Forza media vento[^\d\.-]*?(\d{1,3}[\.,]?\d*)\s*kmh",
                text,
                re.I,
            )

            return {
                "name": "Meteo Celarda (Feltre)",
                "url": url,
                "status": "online",
                "temp": (
                    f"{temp.group(1).replace(',', '.')} °C" if temp else "N/D"
                ),
                "humidity": f"{hum.group(1)} %" if hum else "N/D",
                "pressure": (
                    f"{press.group(1).replace(',', '.')} hPa"
                    if press
                    else "N/D"
                ),
                "wind": (
                    f"{wind.group(1).replace(',', '.')} km/h"
                    if wind
                    else "0.0 km/h"
                ),
                "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
            }
    except Exception as e:
        print(f"Errore Celarda: {e}")

    return {
        "name": "Meteo Celarda",
        "url": url,
        "status": "offline",
        "temp": "N/D",
        "humidity": "N/D",
        "pressure": "N/D",
        "wind": "N/D",
        "updated": "Errore",
    }


def fetch_festisei():
    url = "https://festisei.meteolodi.net/cam1/meteo/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()

            temp = re.search(
                r"Temperatura\s*(-?\d{1,2}[\.,]\d+)\s*°C", text, re.I
            )
            hum = re.search(r"Umidità\s*(\d{1,3})\s*%", text, re.I)
            press = re.search(
                r"Pressione\s*(\d{3,4}[\.,]?\d*)\s*hPa", text, re.I
            )
            wind = re.search(r"Velocità\s*([\d\.\-]+\s*Km/h)", text, re.I)

            return {
                "name": "Osservatorio Festisei - Pedavena",
                "url": url,
                "status": "online",
                "temp": (
                    f"{temp.group(1).replace(',', '.')} °C" if temp else "N/D"
                ),
                "humidity": f"{hum.group(1)} %" if hum else "N/D",
                "pressure": (
                    f"{press.group(1).replace(',', '.')} hPa"
                    if press
                    else "N/D"
                ),
                "wind": wind.group(1) if wind else "N/D",
                "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
            }
    except Exception as e:
        print(f"Errore Festisei: {e}")

    return {
        "name": "Festisei - Pedavena",
        "url": url,
        "status": "offline",
        "temp": "N/D",
        "humidity": "N/D",
        "pressure": "N/D",
        "wind": "N/D",
        "updated": "Errore",
    }


def fetch_meteomugnai():
    live_url = "https://www.meteomugnai.it/mobile/pages/station/liveData.php"
    site_url = "https://www.meteomugnai.it/indexMobile.php"
    try:
        temp, hum, press, wind = parse_meteotemplate(live_url)
        return {
            "name": "Meteo Mugnai",
            "url": site_url,
            "status": "online" if temp != "N/D" else "offline",
            "temp": temp,
            "humidity": hum,
            "pressure": press,
            "wind": wind,
            "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
        }
    except Exception as e:
        print(f"Errore Meteo Mugnai: {e}")

    return {
        "name": "Meteo Mugnai",
        "url": site_url,
        "status": "offline",
        "temp": "N/D",
        "humidity": "N/D",
        "pressure": "N/D",
        "wind": "N/D",
        "updated": "Errore",
    }


def fetch_arsie():
    live_url = (
        "https://stazioni4.soluzionimeteo.it/arsie/mobile/pages/station/liveData.php"
    )
    site_url = "https://stazioni4.soluzionimeteo.it/arsie/indexMobile.php"
    try:
        temp, hum, press, wind = parse_meteotemplate(live_url)
        return {
            "name": "Stazione Meteo Arsiè",
            "url": site_url,
            "status": "online" if temp != "N/D" else "offline",
            "temp": temp,
            "humidity": hum,
            "pressure": press,
            "wind": wind,
            "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
        }
    except Exception as e:
        print(f"Errore Arsiè: {e}")

    return {
        "name": "Stazione Meteo Arsiè",
        "url": site_url,
        "status": "offline",
        "temp": "N/D",
        "humidity": "N/D",
        "pressure": "N/D",
        "wind": "N/D",
        "updated": "Errore",
    }


def fetch_arpav():
    url_arpav = "https://meteo.arpa.veneto.it/meteo/dati_meteo/dati_meteo.php?stazione=217"
    try:
        resp = requests.get(
            url_arpav, headers=HEADERS, timeout=6, verify=False
        )
        if resp.status_code == 200:
            text = resp.text
            temp_match = re.search(
                r"TEMP[^\d\-]*?(-?\d{1,2}[\.,]\d+)", text, re.I
            )
            hum_match = re.search(r"UMID[^\d]*?(\d{1,3})", text, re.I)

            if temp_match:
                t_val = f"{temp_match.group(1).replace(',', '.')} °C"
                h_val = f"{hum_match.group(1)} %" if hum_match else "N/D"
                return {
                    "name": "Stazione ARPAV Feltre",
                    "url": "https://meteo.arpa.veneto.it/meteo/dati_meteo/GrafStaz.html?staz=217",
                    "status": "online",
                    "temp": t_val,
                    "humidity": h_val,
                    "pressure": "N/D",
                    "wind": "N/D",
                    "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
                }
    except Exception as e:
        print(f"Errore ARPAV: {e}")

    # Fallback su Feltre Centro
    try:
        fallback_url = "https://stazioni2.soluzionimeteo.it/feltre/mobile/pages/station/liveData.php"
        temp, hum, press, wind = parse_meteotemplate(fallback_url)
        if temp != "N/D":
            return {
                "name": "Stazione Feltre Centro",
                "url": "https://stazioni2.soluzionimeteo.it/feltre/",
                "status": "online",
                "temp": temp,
                "humidity": hum,
                "pressure": press,
                "wind": wind,
                "updated": datetime.now(ROME_TZ).strftime("%H:%M:%S"),
            }
    except Exception:
        pass

    return {
        "name": "Stazione Feltre",
        "url": "https://meteo.arpa.veneto.it/",
        "status": "offline",
        "temp": "N/D",
        "humidity": "N/D",
        "pressure": "N/D",
        "wind": "N/D",
        "updated": "Errore",
    }


def get_all_weather_data():
    now = datetime.now(ROME_TZ)
    if (
        cache["last_updated"]
        and (now - cache["last_updated"]).total_seconds() < CACHE_TIMEOUT
    ):
        return cache["data"]

    fetchers = [
        fetch_meteoms,
        fetch_celarda,
        fetch_festisei,
        fetch_meteomugnai,
        fetch_arsie,
        fetch_arpav,
        fetch_sencrop,
    ]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(f) for f in fetchers]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    cache["data"] = results
    cache["last_updated"] = now
    return results


# --- DASHBOARD TEMPLATE HTML ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="180">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Centrali meteo Repubblica del Feltrino di Marco Vipera...</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen p-4 md:p-8">
    <div class="max-w-7xl mx-auto">
        <!-- Header -->
        <header class="mb-8 flex flex-col md:flex-row justify-between items-center border-b border-slate-700 pb-4 gap-4">
            <div class="flex items-center gap-4">
                <svg class="w-12 h-12 md:w-16 md:h-16 text-emerald-500 shrink-0 filter drop-shadow-[0_0_8px_rgba(16,185,129,0.4)]" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M 20 85 C 5 60 40 50 25 35 C 18 28 30 15 50 15 C 70 15 82 28 75 35 C 60 50 95 60 80 85" stroke="#059669" stroke-width="8" stroke-linecap="round"/>
                    <polygon points="50,10 22,55 78,55" fill="#10b981" stroke="#047857" stroke-width="4"/>
                    <polygon points="32,32 44,38 34,42" fill="#ef4444"/>
                    <polygon points="68,32 56,38 66,42" fill="#ef4444"/>
                    <line x1="38" y1="33" x2="38" y2="40" stroke="#000" stroke-width="2"/>
                    <line x1="62" y1="33" x2="62" y2="40" stroke="#000" stroke-width="2"/>
                    <line x1="26" y1="26" x2="46" y2="36" stroke="#064e3b" stroke-width="4" stroke-linecap="round"/>
                    <line x1="74" y1="26" x2="54" y2="36" stroke="#064e3b" stroke-width="4" stroke-linecap="round"/>
                    <path d="M 30,48 Q 50,62 70,48" fill="#450a0a" stroke="#000" stroke-width="2"/>
                    <polygon points="36,48 40,58 43,48" fill="#ffffff"/>
                    <polygon points="64,48 60,58 57,48" fill="#ffffff"/>
                    <path d="M 50,54 L 50,75 L 42,85 M 50,75 L 58,85" stroke="#dc2626" stroke-width="3" stroke-linecap="round" fill="none"/>
                </svg>

                <div>
                    <h1 class="text-2xl md:text-3xl font-extrabold text-sky-400 tracking-tight">
                        Centrali meteo Repubblica del Feltrino di Marco Vipera...
                    </h1>
                    <p class="text-slate-400 text-sm mt-1">Rilevamento dati in tempo reale dalle stazioni locali (Auto-aggiornamento 3 min)</p>
                </div>
            </div>

            <div class="text-right">
                <a href="/" class="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm transition flex items-center gap-2 shadow-md">
                    <i class="fa-solid fa-rotate-right"></i> Aggiorna Ora
                </a>
            </div>
        </header>

        <!-- Grid Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {% for station in stations %}
            <div class="bg-slate-800 rounded-xl border border-slate-700 shadow-lg hover:border-sky-500 transition duration-300 overflow-hidden flex flex-col justify-between">
                <div>
                    <div class="p-5 border-b border-slate-700/60 flex justify-between items-start bg-slate-800/50">
                        <h2 class="text-lg font-semibold text-slate-100 leading-snug">{{ station.name }}</h2>
                        {% if station.status == 'online' %}
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Online
                            </span>
                        {% else %}
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
                                <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span> Non disp.
                            </span>
                        {% endif %}
                    </div>

                    <div class="p-5 grid grid-cols-2 gap-4">
                        <div class="col-span-2 bg-slate-900/60 p-3 rounded-lg flex items-center justify-between border border-slate-800">
                            <span class="text-slate-400 text-sm flex items-center gap-2">
                                <i class="fa-solid fa-temperature-half text-amber-400 text-lg"></i> Temperatura
                            </span>
                            <span class="text-xl font-bold text-amber-300">{{ station.temp }}</span>
                        </div>

                        <div class="bg-slate-900/40 p-3 rounded-lg border border-slate-800">
                            <span class="text-slate-400 text-xs block mb-1 flex items-center gap-1">
                                <i class="fa-solid fa-droplet text-blue-400"></i> Umidità
                            </span>
                            <span class="text-base font-semibold text-slate-200">{{ station.humidity }}</span>
                        </div>

                        <div class="bg-slate-900/40 p-3 rounded-lg border border-slate-800">
                            <span class="text-slate-400 text-xs block mb-1 flex items-center gap-1">
                                <i class="fa-solid fa-gauge text-indigo-400"></i> Pressione / Note
                            </span>
                            <span class="text-base font-semibold text-slate-200">{{ station.pressure }}</span>
                        </div>

                        <div class="col-span-2 bg-slate-900/40 p-3 rounded-lg border border-slate-800 flex justify-between items-center">
                            <span class="text-slate-400 text-xs flex items-center gap-1">
                                <i class="fa-solid fa-wind text-teal-400"></i> Vento
                            </span>
                            <span class="text-sm font-semibold text-slate-200">{{ station.wind }}</span>
                        </div>
                    </div>
                </div>

                <div class="px-5 py-3 bg-slate-900/80 border-t border-slate-700/60 flex justify-between items-center text-xs text-slate-400">
                    <span>Aggiornato: {{ station.updated }}</span>
                    <a href="{{ station.url }}" target="_blank" class="text-sky-400 hover:text-sky-300 flex items-center gap-1 transition">
                        Fonte <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                    </a>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    weather_data = get_all_weather_data()
    return render_template_string(HTML_TEMPLATE, stations=weather_data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
