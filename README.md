# Maarif Kindle Plugin

Kindle 10th gen + KOReader için günlük bilgi panosu.

```
┌────────────────────────────────┐
│  12:30   ☀ 81°   17:30        │
│ Yerel Saat      Türkiye Saati  │
│ ┌───┐   EYLÜL          ┌───┐  │
│ │Nam│                  │Hav│  │
│ │az │       27         │a  │  │
│ │Vak│                  │Dur│  │
│ │it.│ CUMARTESİ        │um │  │
│ └───┘                  └───┘  │
│       Sakarya'nın Kurtuluşu   │
│   "Bir dilin sınırları..."    │
│  ✕ 🔋%28  °C °F  ☀  🔦🌙    │
└────────────────────────────────┘
```

## Özellikler

| Kontrol | Eylem |
|---------|-------|
| `✕` (sol alt) | Önceki ekrana dön |
| `°C / °F` | Hava durumu birimini değiştir |
| `○ ☀ ☀☀` | Kindle parlaklığını döngüsel değiştir |
| `🔦 🌙` | Açık / Koyu tema |

## Repo yapısı

```
maarif-kindle/
├── .github/workflows/update_data.yml  # Günlük GitHub Action
├── data/today.json                    # Actions tarafından üretilir
├── quotes/quotes_tr.json              # Türkçe/İslami sözler (elle düzenlenir)
├── scripts/fetch_data.py              # Veri toplama scripti
├── plugin/maarif.koplugin/            # KOReader plugin dosyaları
│   ├── _meta.lua
│   ├── main.lua
│   └── maarifwidget.lua
└── web/maarif.html                    # Tarayıcıda önizleme
```

## Kurulum

### 1. GitHub repo

1. Bu repoyu GitHub'da oluşturun (public).
2. `plugin/maarif.koplugin/maarifwidget.lua` içindeki `YOUR_USERNAME` satırını kendi kullanıcı adınızla değiştirin:
   ```lua
   local DATA_URL = "https://YOUR_USERNAME.github.io/maarif-kindle/today.json"
   ```

### 2. GitHub Pages

Repo **Settings → Pages**'e gidin:
- Source: **GitHub Actions**

İlk Actions çalışmasından sonra `data/today.json` dosyası yayınlanacak.

### 3. Actions'ı etkinleştirin

`.github/workflows/update_data.yml` her sabah 05:00 UTC'de (Reston gece yarısı) otomatik çalışır.
Manuel tetiklemek için: **Actions → Update Daily Data → Run workflow**.

### 4. Plugin kurulumu (Kindle)

1. Kindle'ı USB ile bilgisayara bağlayın.
2. `plugin/maarif.koplugin/` klasörünü Kindle'daki `koreader/plugins/` dizinine kopyalayın.
3. KOReader'ı açın → **Menü → Araçlar → Maarif Ekranı**.

### 5. Fontlar (opsiyonel — görünümü iyileştirir)

Figma tasarımındaki fontları kullanmak için aşağıdakileri indirip
`koreader/fonts/` dizinine kopyalayın:
- [Merriweather](https://fonts.google.com/specimen/Merriweather)
- [Sofia Sans](https://fonts.google.com/specimen/Sofia+Sans)
- [Sofia Sans Extra Condensed](https://fonts.google.com/specimen/Sofia+Sans+Extra+Condensed)

Font isimlerini `maarifwidget.lua` içinde `"NotoSerif-Bold"` → `"Merriweather-Bold"` olarak güncelleyin.

## Veri kaynakları

| Veri | Kaynak | API anahtarı |
|------|--------|--------------|
| Namaz vakitleri | [Aladhan](https://aladhan.com/prayer-times-api) | Yok |
| Hava durumu | [Open-Meteo](https://open-meteo.com/) | Yok |
| Tarihte bugün | Predefined JSON + [Wikipedia API](https://en.wikipedia.org/api/rest_v1/) | Yok |
| Özlü sözler | `quotes/quotes_tr.json` + [ZenQuotes](https://zenquotes.io/) | Yok |

Tüm API'ler **ücretsiz ve anahtar gerektirmez**.

## Sözleri genişletmek

`quotes/quotes_tr.json` dosyasına JSON nesnesi ekleyin:
```json
{"text": "Söylediğin kadar...", "author": "Adı"}
```

## Türkçe tarih veritabanı

`scripts/fetch_data.py` içindeki `TURKISH_HISTORY` sözlüğüne
`"MM-DD": "Olay adı"` formatında yeni olaylar eklenebilir.
