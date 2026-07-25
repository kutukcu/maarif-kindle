#!/usr/bin/env python3
"""
Maarif daily data fetcher.
Runs via GitHub Actions; outputs data/today.json.
"""

from __future__ import annotations

import calendar
import json
import os
import random
import sys
from datetime import datetime, timezone, timedelta

import requests

# ── Location ────────────────────────────────────────────────────────────────
LAT = 38.9687
LON = -77.3411
CITY = "Reston"
COUNTRY = "US"
STATE = "Virginia"
TIMEZONE = "America/New_York"

# ── Locale tables ────────────────────────────────────────────────────────────
MONTHS_TR = [
    "", "OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN",
    "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK",
]
WEEKDAYS_TR = ["PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"]

# ── Open-Meteo weather code → icon key ──────────────────────────────────────
WMO_ICON = {
    0: "sun", 1: "sun", 2: "cloud_sun", 3: "cloud",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "heavy_rain",
    71: "snow", 73: "snow", 75: "heavy_snow", 77: "snow",
    80: "rain", 81: "rain", 82: "heavy_rain",
    85: "snow", 86: "heavy_snow",
    95: "storm", 96: "storm", 99: "storm",
}

# ── Turkish national / historical events, keyed by MM-DD ────────────────────
TURKISH_HISTORY = {
    "01-01": "Yeni Yıl",
    "01-10": "Çalışan Gazeteciler Günü",
    "02-18": "Çanakkale Deniz Savaşı (1915)",
    "03-08": "Dünya Kadınlar Günü",
    "03-18": "Çanakkale Zaferi ve Şehitleri Anma Günü",
    "03-31": "Ermeni Pogromu Yıl Dönümü",
    "04-01": "Edirne'nin Kurtuluşu (1920)",
    "04-11": "Osmanlı Anayasası'nın İlanı (1876)",
    "04-23": "Ulusal Egemenlik ve Çocuk Bayramı",
    "05-01": "Emek ve Dayanışma Günü",
    "05-03": "Dünya Basın Özgürlüğü Günü",
    "05-15": "İzmir'in İşgali (1919)",
    "05-19": "Atatürk'ü Anma, Gençlik ve Spor Bayramı",
    "05-27": "1960 Askeri Darbesi",
    "06-15": "Kıbrıs Cumhurbaşkanlığı Seçimi",
    "07-01": "Denizcilik ve Kabotaj Bayramı",
    "07-15": "Demokrasi ve Milli Birlik Günü",
    "07-20": "Kıbrıs Barış Harekâtı (1974)",
    "08-26": "Büyük Taarruz (1922)",
    "08-30": "Zafer Bayramı",
    "09-05": "Adapazarı'nın Kurtuluşu (1922)",
    "09-06": "İstanbul Pogromu (1955)",
    "09-09": "İzmir'in Kurtuluşu (1922)",
    "09-12": "1980 Askeri Darbesi",
    "09-13": "Sakarya'nın Kurtuluşu (1922)",
    "09-16": "Kars'ın Kurtuluşu (1920)",
    "09-18": "Bursa'nın Kurtuluşu (1922)",
    "09-23": "Sivas Olayları (1919)",
    "10-06": "İstanbul'un Kurtuluşu (1923)",
    "10-13": "Ankara'nın Başkent İlan Edilmesi (1923)",
    "10-18": "Mudanya Ateşkesi (1922)",
    "10-29": "Cumhuriyet Bayramı",
    "11-10": "Atatürk'ü Anma Günü",
    "11-24": "Öğretmenler Günü",
    "12-02": "Bandırma Vapuru'nun İstanbul'dan Ayrılışı (1918)",
    "12-25": "Noel",
    "12-31": "Yılbaşı Arifesi",
}

# ── ABD'de aileyi ilgilendiren, sabit tarihli günler ────────────────────────
US_HOUSEHOLD_FIXED = {
    "01-27": "Vergi Beyan Dönemi Başlıyor (tahmini)",
    "06-19": "Juneteenth (Resmi Tatil)",
    "07-04": "Amerika Bağımsızlık Günü",
    "10-31": "Halloween",
    "11-11": "Gaziler Günü / Veterans Day (Resmi Tatil)",
}

# ── Hicri takvime göre dini gün/kandiller — (ay, gün) → isim ────────────────
# Not: Gerçek Diyanet tarihleri ru'yet-i hilal'e (ay gözlemi) göre 1 gün
# kayabilir; burada hesaplanan hicri tarih (Aladhan gToH) baz alınıyor.
HIJRI_EVENTS = {
    (1, 1):   "Hicri Yılbaşı",
    (1, 10):  "Aşure Günü",
    (3, 12):  "Mevlid Kandili",
    (7, 27):  "Miraç Kandili",
    (8, 15):  "Berat Kandili",
    (9, 1):   "Ramazan Ayı Başlangıcı",
    (9, 27):  "Kadir Gecesi",
    (10, 1):  "Ramazan Bayramı (1. Gün)",
    (10, 2):  "Ramazan Bayramı (2. Gün)",
    (10, 3):  "Ramazan Bayramı (3. Gün)",
    (12, 10): "Kurban Bayramı (1. Gün)",
    (12, 11): "Kurban Bayramı (2. Gün)",
    (12, 12): "Kurban Bayramı (3. Gün)",
    (12, 13): "Kurban Bayramı (4. Gün)",
}


def hijri_event_name(hijri_month: int, hijri_day: int, gregorian_weekday: int) -> str | None:
    # Regaib Kandili, Recep ayının ilk Cuma gecesidir — sabit gün değil.
    if hijri_month == 7 and 1 <= hijri_day <= 7 and gregorian_weekday == 4:
        return "Regaib Kandili"
    return HIJRI_EVENTS.get((hijri_month, hijri_day))


def get_hijri_event(date_str: str, gregorian_weekday: int) -> str | None:
    """date_str format DD-MM-YYYY. Aladhan'ın miladi→hicri çevrimini kullanır."""
    try:
        r = requests.get(f"https://api.aladhan.com/v1/gToH/{date_str}", timeout=10)
        r.raise_for_status()
        h = r.json()["data"]["hijri"]
        return hijri_event_name(int(h["month"]["number"]), int(h["day"]), gregorian_weekday)
    except Exception as e:
        print(f"[hijri] {e}", file=sys.stderr)
        return None


def nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    """weekday: 0=Pazartesi..6=Pazar. n=1 → ayın ilk X günü, n=-1 → son X günü."""
    if n > 0:
        d = datetime(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return d + timedelta(days=offset + (n - 1) * 7)
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day)
    offset = (d.weekday() - weekday) % 7
    return d - timedelta(days=offset)


def tax_day(year: int) -> datetime:
    """ABD vergi ödeme son günü — 15 Nisan, hafta sonuna denk gelirse ertelenir."""
    d = datetime(year, 4, 15)
    if d.weekday() == 5:      # Cumartesi
        d += timedelta(days=2)
    elif d.weekday() == 6:    # Pazar
        d += timedelta(days=1)
    return d


def build_us_household_days(year: int) -> dict:
    days = dict(US_HOUSEHOLD_FIXED)

    variable = {
        nth_weekday(year, 1, 0, 3):   "Martin Luther King Günü (Resmi Tatil)",
        nth_weekday(year, 2, 0, 3):   "Başkanlar Günü (Resmi Tatil)",
        nth_weekday(year, 5, 0, -1):  "Anma Günü / Memorial Day (Resmi Tatil)",
        nth_weekday(year, 9, 0, 1):   "Emek Günü / Labor Day (Resmi Tatil, Okullar Başlıyor)",
        nth_weekday(year, 10, 0, 2):  "Columbus Günü (Resmi Tatil)",
        nth_weekday(year, 11, 3, 4):  "Şükran Günü / Thanksgiving (Resmi Tatil)",
        tax_day(year):                "Vergi Ödemelerinin Son Günü",
        nth_weekday(year, 3, 6, 2):   "Yaz Saati Başlıyor (Saatler 1 Saat İleri)",
        nth_weekday(year, 11, 6, 1):  "Yaz Saati Bitiyor (Saatler 1 Saat Geri)",
    }
    for d, name in variable.items():
        days[d.strftime("%m-%d")] = name

    return days


def get_prayer_times(date_str: str) -> dict | None:
    """Aladhan API — method 2 = ISNA (North America)."""
    try:
        r = requests.get(
            f"https://api.aladhan.com/v1/timingsByCity/{date_str}",
            params={"city": CITY, "country": COUNTRY, "state": STATE, "method": 2},
            timeout=15,
        )
        r.raise_for_status()
        t = r.json()["data"]["timings"]
        return {
            "imsak":  t["Imsak"][:5],
            "gunes":  t["Sunrise"][:5],
            "ogle":   t["Dhuhr"][:5],
            "ikindi": t["Asr"][:5],
            "aksam":  t["Maghrib"][:5],
            "yatsi":  t["Isha"][:5],
        }
    except Exception as e:
        print(f"[prayer] {e}", file=sys.stderr)
        return None


def get_weather(now_et: datetime) -> dict | None:
    """Open-Meteo — free, no API key."""
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": LAT, "longitude": LON,
                "current": "temperature_2m,weathercode",
                "daily": "weathercode,temperature_2m_max",
                "temperature_unit": "fahrenheit",
                "timezone": TIMEZONE,
                "forecast_days": 7,
            },
            timeout=15,
        )
        r.raise_for_status()
        d = r.json()

        cur_f = round(d["current"]["temperature_2m"])
        cur_c = round((cur_f - 32) * 5 / 9)
        cur_code = d["current"]["weathercode"]

        forecast = []
        for i in range(1, 7):
            if i >= len(d["daily"]["time"]):
                break
            date_obj = datetime.fromisoformat(d["daily"]["time"][i])
            wd = date_obj.weekday()  # 0=Mon … 6=Sun
            tr_days = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
            day_name = "Yarın" if i == 1 else tr_days[wd]
            tf = round(d["daily"]["temperature_2m_max"][i])
            tc = round((tf - 32) * 5 / 9)
            code = d["daily"]["weathercode"][i]
            forecast.append({
                "day_tr": day_name,
                "condition": WMO_ICON.get(code, "cloud"),
                "condition_code": code,
                "temp_f": tf,
                "temp_c": tc,
            })

        return {
            "temp_f": cur_f,
            "temp_c": cur_c,
            "condition": WMO_ICON.get(cur_code, "cloud"),
            "condition_code": cur_code,
            "forecast": forecast,
        }
    except Exception as e:
        print(f"[weather] {e}", file=sys.stderr)
        return None


def get_wikipedia_tr_event(month: int, day: int) -> str | None:
    """Curated listelerde eşleşme yoksa Türkçe Wikipedia'nın 'Tarihte Bugün'ünden
    rastgele bir olay — tamamen Türkçe, İngilizce Wikipedia'nın yerine bu kullanılıyor."""
    try:
        r = requests.get(
            f"https://tr.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}",
            headers={"User-Agent": "MaarifKindlePlugin/1.0 (tolga@pyde.tech)"},
            timeout=10,
        )
        r.raise_for_status()
        events = r.json().get("events", [])
        if not events:
            return None
        ev = random.choice(events[:10])
        return f"{ev['year']}: {ev['text'][:90]}"
    except Exception as e:
        print(f"[history/wikipedia-tr] {e}", file=sys.stderr)
        return None


def get_history(now_et: datetime) -> dict:
    """Günün öne çıkan olayını seçer. Öncelik sırası:
    1) Dini bayram/kandil (hicri takvim, kayan tarihli)
    2) ABD'de aileyi ilgilendiren pratik gün (vergi, resmi tatil vb.)
    3) Türkiye'nin resmi/milli günü (sabit tarihli)
    4) Hiçbiri yoksa Türkçe Wikipedia'nın "Tarihte Bugün"ünden rastgele bir olay
    5) O da yoksa genel "Tarihte Bugün" yazısı.
    Tamamı Türkçe — dış kaynaktan ham İngilizce metin çekilmez.
    """
    key = f"{now_et.month:02d}-{now_et.day:02d}"
    date_str = now_et.strftime("%d-%m-%Y")

    hijri_event   = get_hijri_event(date_str, now_et.weekday())
    us_event      = build_us_household_days(now_et.year).get(key)
    turkish_event = TURKISH_HISTORY.get(key)

    wiki_event = None
    if not (hijri_event or us_event or turkish_event):
        wiki_event = get_wikipedia_tr_event(now_et.month, now_et.day)

    return {
        "title": hijri_event or us_event or turkish_event or wiki_event or "Tarihte Bugün",
        "hijri": hijri_event,
        "us": us_event,
        "turkish": turkish_event,
        "wiki": wiki_event,
    }


def get_quote() -> dict:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    quotes_file = os.path.join(script_dir, "../quotes/quotes_tr.json")

    quotes_tr = []
    if os.path.exists(quotes_file):
        with open(quotes_file, encoding="utf-8") as f:
            quotes_tr = json.load(f)

    use_tr = quotes_tr and random.random() < 0.70

    if use_tr:
        return random.choice(quotes_tr)

    try:
        r = requests.get("https://zenquotes.io/api/random", timeout=8)
        if r.status_code == 200:
            d = r.json()[0]
            return {"text": d["q"], "author": d["a"]}
    except Exception as e:
        print(f"[quote/zenquotes] {e}", file=sys.stderr)

    if quotes_tr:
        return random.choice(quotes_tr)

    return {"text": "Bilgi ile amel etmek gerektir.", "author": "Mevlâna"}


def main() -> None:
    # Use ET as the "home" timezone for date calculations
    try:
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo(TIMEZONE))
        now_utc = datetime.now(timezone.utc)
        now_tr = datetime.now(ZoneInfo("Europe/Istanbul"))
    except ImportError:
        # Fallback (Python < 3.9 or missing tzdata)
        now_et = datetime.utcnow() - timedelta(hours=4)  # rough ET
        now_utc = datetime.utcnow()
        now_tr = datetime.utcnow() + timedelta(hours=3)

    month = now_et.month
    day = now_et.day
    weekday = now_et.weekday()  # 0=Mon … 6=Sun

    date_str = now_et.strftime("%d-%m-%Y")

    prayer_times = get_prayer_times(date_str)
    weather = get_weather(now_et)
    history = get_history(now_et)
    quote = get_quote()

    data = {
        "generated_at": now_utc.isoformat(),
        "date": {
            "day": day,
            "month": month,
            "month_tr": MONTHS_TR[month],
            "weekday_tr": WEEKDAYS_TR[weekday],
            "iso": now_et.strftime("%Y-%m-%d"),
        },
        "prayer_times": prayer_times or {
            "imsak": "--:--", "gunes": "--:--", "ogle": "--:--",
            "ikindi": "--:--", "aksam": "--:--", "yatsi": "--:--",
        },
        "weather": weather or {
            "temp_f": 0, "temp_c": 0,
            "condition": "cloud", "condition_code": 0,
            "forecast": [],
        },
        "history": history,
        "quote": quote,
    }

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "today.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✓ Written {out_path}")


if __name__ == "__main__":
    main()
