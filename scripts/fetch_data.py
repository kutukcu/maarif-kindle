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

# ── Türkiye'nin resmi tatilleri + dini bayramlar (Nager.Date'ten canlı çekilir,
# ── hükûmetin resmen ilan ettiği/Diyanet'le uyumlu tarihler — bkz. get_public_holidays)

# Resmi tatil olmayan ama önemli gün/haftalar — sabit veya kayan (Anneler/Babalar Günü).
TR_IMPORTANT_DAYS_FIXED = {
    "03-08": "Dünya Kadınlar Günü",
    "11-24": "Öğretmenler Günü",
}

# ── ABD'nin resmi tatilleri de Nager.Date'ten canlı çekilir (bkz. US_SKIP_NAMES / US_HOLIDAY_TR_NAMES).
# Nager, hafta sonuna denk gelen sabit tarihli tatilleri "gözlemlenen" güne kaydırıyor
# (ör. 4 Temmuz Cumartesi'yse 3 Temmuz'u veriyor). Ailenin gerçek kültürel günü bilmesi
# için bu 5 sabit tarihli günü kendimiz, gerçek takvim tarihiyle veriyoruz; Nager'daki
# karşılıklarını da bu yüzden atlıyoruz (US_SKIP_NAMES).
US_FIXED_OVERRIDE = {
    "01-01": "Amerika'da Yeni Yıl (Resmi Tatil)",
    "06-19": "Juneteenth (Resmi Tatil)",
    "07-04": "Amerika Bağımsızlık Günü (Resmi Tatil)",
    "11-11": "Gaziler Günü / Veterans Day (Resmi Tatil)",
    "12-25": "Amerika'da Noel (Resmi Tatil)",
}
US_SKIP_NAMES = {
    "New Year's Day", "Juneteenth National Independence Day",
    "Independence Day", "Veterans Day", "Christmas Day",
}
US_HOLIDAY_TR_NAMES = {
    "Martin Luther King, Jr. Day": "Martin Luther King Günü (Resmi Tatil)",
    "Washington's Birthday": "Başkanlar Günü (Resmi Tatil)",
    "Memorial Day": "Anma Günü / Memorial Day (Resmi Tatil)",
    "Labour Day": "Emek Günü / Labor Day (Resmi Tatil, Okullar Başlıyor)",
    "Columbus Day": "Columbus Günü (Resmi Tatil)",
    "Thanksgiving Day": "Şükran Günü / Thanksgiving (Resmi Tatil)",
}

# Resmi tatil olmayan ama aileyi ilgilendiren ABD günleri.
US_IMPORTANT_DAYS_FIXED = {
    "01-27": "Vergi Beyan Dönemi Başlıyor (tahmini)",
    "10-31": "Halloween",
}


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


def get_public_holidays(country_code: str, year: int) -> dict:
    """Nager.Date — ücretsiz, anahtarsız açık kaynak resmi tatil API'si.
    Türkiye için dini bayramlar dahil (hükûmetin resmen ilan ettiği/Diyanet'le
    uyumlu tarihler); ABD için sadece ülke geneli (global) tatiller alınır,
    eyalete özgü olanlar (ör. Lincoln's Birthday) elenir."""
    try:
        r = requests.get(
            f"https://date.nager.at/api/v3/publicholidays/{year}/{country_code}",
            timeout=10,
        )
        r.raise_for_status()
        return {h["date"]: h for h in r.json() if h.get("global")}
    except Exception as e:
        print(f"[holidays/{country_code}] {e}", file=sys.stderr)
        return {}


def build_turkish_days(now_et: datetime, tr_holidays: dict) -> str | None:
    iso = now_et.strftime("%Y-%m-%d")
    key = now_et.strftime("%m-%d")

    h = tr_holidays.get(iso)
    if h:
        return h["localName"]
    return TR_IMPORTANT_DAYS_FIXED.get(key)


def build_us_days(now_et: datetime, us_holidays: dict) -> str | None:
    iso = now_et.strftime("%Y-%m-%d")
    key = now_et.strftime("%m-%d")

    fixed = US_FIXED_OVERRIDE.get(key)
    if fixed:
        return fixed

    h = us_holidays.get(iso)
    if h and h["name"] not in US_SKIP_NAMES:
        tr_name = US_HOLIDAY_TR_NAMES.get(h["name"])
        if tr_name:
            return tr_name

    if key == tax_day(now_et.year).strftime("%m-%d"):
        return "Vergi Ödemelerinin Son Günü"
    return US_IMPORTANT_DAYS_FIXED.get(key)


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
                "hourly": "temperature_2m,weathercode",
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

        # Widget verisi sadece her 6 saatte bir (00/06/12/18) yenilendiği için,
        # bir sonraki yenilemeye kadar geçerli olacak 6 saatlik pencereyi veriyoruz.
        hourly_times = d["hourly"]["time"]
        now_hour_iso = now_et.strftime("%Y-%m-%dT%H:00")
        start_idx = hourly_times.index(now_hour_iso) if now_hour_iso in hourly_times else 0

        hourly = []
        for i in range(start_idx, start_idx + 6):
            if i >= len(hourly_times):
                break
            dt = datetime.fromisoformat(hourly_times[i])
            tf = round(d["hourly"]["temperature_2m"][i])
            tc = round((tf - 32) * 5 / 9)
            code = d["hourly"]["weathercode"][i]
            hourly.append({
                "hour": dt.strftime("%H:00"),
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
            "hourly": hourly,
        }
    except Exception as e:
        print(f"[weather] {e}", file=sys.stderr)
        return None


def _short(s: str) -> str:
    """Birleştirirken '(Resmi Tatil...)' gibi ekleri kırp, satır kısa kalsın."""
    return s.split(" (Resmi Tatil")[0]


def get_history(now_et: datetime) -> dict:
    """Günün öne çıkan gününü seçer — sadece Türkiye ve ABD'nin milli/dini/resmi
    tatilleri ile önemli gün ve haftaları.
    1) Türkiye'nin resmi tatili / dini bayramı (Nager.Date, Diyanet'le uyumlu)
    2) ABD'nin resmi tatili / aileyi ilgilendiren günü (vergi vb.)
    İkisi aynı güne denk gelirse ikisi birden "Türkiye / ABD" biçiminde gösterilir.
    Hiçbiri yoksa title None döner — boşken ne gösterileceğine tüketen taraf karar verir.
    Tamamı Türkçe.
    """
    tr_holidays = get_public_holidays("TR", now_et.year)
    us_holidays = get_public_holidays("US", now_et.year)

    turkish_event = build_turkish_days(now_et, tr_holidays)
    us_event      = build_us_days(now_et, us_holidays)

    if turkish_event and us_event:
        title = f"{_short(turkish_event)} / {_short(us_event)}"
    else:
        title = turkish_event or us_event or None

    return {
        "title": title,
        "turkish": turkish_event,
        "us": us_event,
    }


def get_quote(now_et: datetime) -> dict:
    """quotes/quotes_tr.json — 366 sözlük tamamen Türkçe liste (dini büyükler
    ve düşünürlerden). Takvim gününü tohum olarak kullanan bir rastgelelik ile
    seçilir: aynı gün içinde (saatlik/30 dakikalık yenilemelerde) hep aynı söz
    gelir, ama günden güne liste sırasına bağlı olmadan rastgele değişir.
    Dış kaynaktan (ZenQuotes vb.) İngilizce söz artık çekilmez.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    quotes_file = os.path.join(script_dir, "../quotes/quotes_tr.json")

    quotes_tr = []
    if os.path.exists(quotes_file):
        with open(quotes_file, encoding="utf-8") as f:
            quotes_tr = json.load(f)

    if not quotes_tr:
        return {"text": "Bilgi ile amel etmek gerektir.", "author": "Mevlâna"}

    day_key = now_et.strftime("%Y-%m-%d")
    return random.Random(day_key).choice(quotes_tr)


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
    quote = get_quote(now_et)

    # Namaz vakti / hava durumu kritik veriler. API'ler geçici olarak
    # başarısız olursa today.json'u sıfırlanmış veriyle ezip yayınlamak
    # yerine işlemi durduruyoruz — böylece Kindle, bir sonraki başarılı
    # çalışmaya kadar elindeki son geçerli veriyi göstermeye devam ediyor.
    if prayer_times is None or weather is None:
        print("✗ Kritik veri alınamadı (namaz vakti veya hava durumu); "
              "today.json güncellenmedi.", file=sys.stderr)
        sys.exit(1)

    data = {
        "generated_at": now_utc.isoformat(),
        "date": {
            "day": day,
            "month": month,
            "month_tr": MONTHS_TR[month],
            "weekday_tr": WEEKDAYS_TR[weekday],
            "iso": now_et.strftime("%Y-%m-%d"),
        },
        "prayer_times": prayer_times,
        "weather": weather,
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
