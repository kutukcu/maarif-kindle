--[[
  MaarifWidget — full-screen display widget for Kindle 10th gen (600×800).
  Draws directly onto the KOReader framebuffer using BlitBuffer + TextWidget.

  Touch zones (bottom bar, left→right):
    [40–80]   ✕  Close / back
    [90–180]  Battery (read-only)
    [240–310] °C / °F toggle
    [320–410] Brightness cycle (kapalı → orta → yüksek)
    [450–560] Theme toggle (light ↔ dark)
--]]

local InputContainer = require("ui/widget/container/inputcontainer")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local FrameContainer  = require("ui/widget/container/framecontainer")
local CenterContainer = require("ui/widget/container/centercontainer")
local TextWidget      = require("ui/widget/textwidget")
local LineWidget      = require("ui/widget/linewidget")
local UIManager       = require("ui/uimanager")
local Screen          = require("device/screen")
local Device          = require("device")
local Blitbuffer      = require("ffi/blitbuffer")
local Geom            = require("ui/geometry")
local GestureRange    = require("ui/gesturerange")
local Font            = require("ui/font")
local logger          = require("logger")

-- ── HTTP helpers ─────────────────────────────────────────────────────────────
local ltn12 = require("ltn12")
local socket_http = require("socket.http")
local ssl_https   = require("ssl.https")

-- ── Data URL — replace YOUR_USERNAME with your GitHub username ───────────────
local DATA_URL   = "https://YOUR_USERNAME.github.io/maarif-kindle/today.json"
local CACHE_FILE = "/mnt/us/koreader/plugins/maarif.koplugin/today_cache.json"

-- ── Locale ──────────────────────────────────────────────────────────────────
local MONTHS_TR  = {"","OCAK","ŞUBAT","MART","NİSAN","MAYIS","HAZİRAN",
                    "TEMMUZ","AĞUSTOS","EYLÜL","EKİM","KASIM","ARALIK"}
local WDAYS_TR   = {"PAZARTESİ","SALI","ÇARŞAMBA","PERŞEMBE","CUMA","CUMARTESİ","PAZAR"}

-- ── Weather icons (Unicode; e-ink renders basic symbols well) ────────────────
local WX_ICON = {
    sun        = "\xE2\x98\x80",  -- ☀  U+2600
    cloud_sun  = "\xE2\x9B\x85",  -- ⛅  U+26C5
    cloud      = "\xE2\x98\x81",  -- ☁  U+2601
    fog        = "~fog~",
    drizzle    = "\xF0\x9F\x8C\xA6", -- 🌦
    rain       = "\xF0\x9F\x8C\xA7", -- 🌧
    heavy_rain = "\xF0\x9F\x8C\xA7",
    snow       = "\xE2\x9D\x84",  -- ❄  U+2744
    heavy_snow = "\xE2\x9D\x84",
    storm      = "\xE2\x9B\x88",  -- ⛈  U+26C8
}

-- ── Brightness levels (0–100 for KOReader frontlight API) ───────────────────
local BR_LEVELS = {0, 50, 100}
local BR_LABELS = {"○", "☀", "☀☀"}

-- ── Widget ──────────────────────────────────────────────────────────────────
local MaarifWidget = InputContainer:extend{
    -- user-toggled state
    unit       = "F",
    theme      = "light",
    br_index   = 2,     -- index into BR_LEVELS
    -- fetched data
    data       = nil,
    battery    = 0,
}

-- ── Colour helpers ───────────────────────────────────────────────────────────
local function colors(theme)
    if theme == "dark" then
        return Blitbuffer.COLOR_BLACK, Blitbuffer.COLOR_WHITE
    end
    return Blitbuffer.COLOR_WHITE, Blitbuffer.COLOR_BLACK
end

-- ── HTTP fetch (supports https) ──────────────────────────────────────────────
local function fetchUrl(url)
    local body = {}
    local client = url:match("^https") and ssl_https or socket_http
    local ok, code = client.request{url = url, sink = ltn12.sink.table(body)}
    if ok and (code == 200 or code == "200") then
        return table.concat(body)
    end
    return nil
end

-- ── JSON (KOReader ships with a JSON lib) ───────────────────────────────────
local function decodeJSON(s)
    local ok, t = pcall(require("json").decode, s)
    return ok and t or nil
end

-- ── Data loading ─────────────────────────────────────────────────────────────
function MaarifWidget:loadData()
    -- 1. Try network fetch
    local raw = fetchUrl(DATA_URL)
    if raw then
        local parsed = decodeJSON(raw)
        if parsed then
            -- Cache to disk
            local f = io.open(CACHE_FILE, "w")
            if f then f:write(raw); f:close() end
            return parsed
        end
    end
    -- 2. Fallback: cached data
    local f = io.open(CACHE_FILE, "r")
    if f then
        local cached = f:read("*a"); f:close()
        local parsed = decodeJSON(cached)
        if parsed then return parsed end
    end
    -- 3. Fallback: bare system data (no prayer/weather)
    local t = os.date("*t")
    return {
        date = {
            day        = t.day,
            month      = t.month,
            month_tr   = MONTHS_TR[t.month],
            weekday_tr = WDAYS_TR[t.wday == 1 and 7 or t.wday - 1],
        },
        prayer_times = {imsak="--:--",gunes="--:--",ogle="--:--",
                        ikindi="--:--",aksam="--:--",yatsi="--:--"},
        weather = {temp_f=0,temp_c=0,condition="cloud",forecast={}},
        history = {title="Tarihte Bugün"},
        quote   = {text="Hayatta en hakiki mürşit ilimdir.",author="Atatürk"},
    }
end

-- ── init ─────────────────────────────────────────────────────────────────────
function MaarifWidget:init()
    local W = Screen:getWidth()
    local H = Screen:getHeight()
    self.dimen = Geom:new{x=0, y=0, w=W, h=H}

    -- Register touch gestures over the full screen
    self.ges_events = {
        Tap  = {GestureRange:new{ges="tap",  range=self.dimen}},
        Hold = {GestureRange:new{ges="hold", range=self.dimen}},
    }

    -- Load data (network → cache → fallback)
    self.data    = self:loadData()
    self.battery = Device:getBatteryCapacity() or 0

    -- Restore frontlight index from current level
    if Device.screen.getFrontlightLevel then
        local cur = Device.screen:getFrontlightLevel() or 50
        if     cur == 0   then self.br_index = 1
        elseif cur <= 60  then self.br_index = 2
        else                   self.br_index = 3
        end
    end
end

-- ── Touch handling ───────────────────────────────────────────────────────────
function MaarifWidget:onTap(_, ges)
    local x = ges.pos.x
    local H = Screen:getHeight()
    local bottom = H - 70     -- bottom control strip starts here

    if ges.pos.y < bottom then return true end   -- ignore taps above strip

    if x < 90 then
        -- ✕ Close
        UIManager:close(self)
        UIManager:setDirty(nil, "full")

    elseif x >= 230 and x < 330 then
        -- °C / °F toggle
        self.unit = (self.unit == "F") and "C" or "F"
        UIManager:setDirty(self, "partial")

    elseif x >= 330 and x < 430 then
        -- Brightness cycle
        self.br_index = (self.br_index % #BR_LEVELS) + 1
        local level = BR_LEVELS[self.br_index]
        if Device.screen.setFrontlightLevel then
            Device.screen:setFrontlightLevel(level)
        end
        UIManager:setDirty(self, "partial")

    elseif x >= 450 then
        -- Theme toggle
        self.theme = (self.theme == "light") and "dark" or "light"
        UIManager:setDirty(self, "full")
    end

    return true
end

-- ── Main paint ───────────────────────────────────────────────────────────────
function MaarifWidget:paintTo(bb, ox, oy)
    local W  = self.dimen.w
    local H  = self.dimen.h
    local BG, FG = colors(self.theme)

    -- Background
    bb:fill(BG)

    -- Double border
    self:_paintBorderRect(bb, 4,  4,  W-8,  H-8,  4, FG)
    self:_paintBorderRect(bb, 16, 16, W-32, H-32, 2, FG)

    -- Populate from data
    local data = self.data or {}
    local d    = data.date         or {}
    local pt   = data.prayer_times or {}
    local wx   = data.weather      or {}
    local hist = data.history      or {}
    local quot = data.quote        or {}

    local month_tr   = d.month_tr   or MONTHS_TR[os.date("*t").month]
    local weekday_tr = d.weekday_tr or WDAYS_TR[os.date("*t").wday == 1 and 7 or os.date("*t").wday - 1]
    local day_num    = tostring(d.day or os.date("*t").day)

    -- ── Clocks ──────────────────────────────────────────────────────────────
    local now  = os.date("*t")
    local local_str = string.format("%d:%02d", now.hour, now.min)
    -- Turkey time: os.time() is always UTC epoch; UTC+3
    local tr_t = os.date("!*t", os.time() + 3*3600)
    local tr_str   = string.format("%d:%02d", tr_t.hour, tr_t.min)

    self:_text(bb, local_str, 128, 72, "NotoSerif-Regular", 40, FG)
    bb:paintRect(38, 87, 180, 2, FG)
    self:_text(bb, "Yerel Saat", 128, 110, "NotoSerif-Bold", 18, FG)

    self:_text(bb, tr_str,    472, 72, "NotoSerif-Regular", 40, FG)
    bb:paintRect(382, 87, 180, 2, FG)
    self:_text(bb, "Türkiye Saati", 472, 110, "NotoSerif-Bold", 18, FG)

    -- ── Centre weather ───────────────────────────────────────────────────────
    local wx_icon = WX_ICON[wx.condition or "cloud"] or "\xE2\x98\x81"
    local wx_temp = (self.unit == "F")
        and string.format("%d°", wx.temp_f or 0)
        or  string.format("%d°", wx.temp_c or 0)
    self:_text(bb, wx_icon,  300, 55, "NotoSans-Regular", 26, FG)
    self:_text(bb, wx_temp,  300, 95, "NotoSerif-Bold",   26, FG)

    -- ── Month name ───────────────────────────────────────────────────────────
    self:_text(bb, month_tr, 300, 215, "NotoSerif-Bold", 62, FG)

    -- ── Giant day number (condensed look via large bold) ─────────────────────
    self:_text(bb, day_num, 300, 570, "NotoSans-Bold", 340, FG)

    -- ── Day name ─────────────────────────────────────────────────────────────
    self:_text(bb, weekday_tr, 300, 640, "NotoSerif-Bold", 52, FG)

    -- ── Left panel: Namaz Vakitleri ───────────────────────────────────────────
    local lp_x, lp_y, lp_w, lp_h = 40, 145, 81, 390
    self:_paintBorderRect(bb, lp_x, lp_y, lp_w, lp_h, 1, FG)
    self:_text(bb, "Namaz",    lp_x + lp_w/2, lp_y + 15, "NotoSerif-Bold", 11, FG)
    self:_text(bb, "Vakitleri",lp_x + lp_w/2, lp_y + 28, "NotoSerif-Bold", 11, FG)
    bb:paintRect(lp_x, lp_y + 40, lp_w, 1, FG)

    local prayers = {
        {"İmsak",  pt.imsak  or "--:--"},
        {"Güneş",  pt.gunes  or "--:--"},
        {"Öğle",   pt.ogle   or "--:--"},
        {"İkindi", pt.ikindi or "--:--"},
        {"Akşam",  pt.aksam  or "--:--"},
        {"Yatsı",  pt.yatsi  or "--:--"},
    }
    local p_start = lp_y + 48
    local p_step  = (lp_h - 50) / #prayers
    for i, p in ipairs(prayers) do
        local py = p_start + (i-1)*p_step + 8
        self:_text(bb, p[1], lp_x + lp_w/2, py,    "NotoSerif-Bold",    10, FG)
        self:_text(bb, p[2], lp_x + lp_w/2, py+14, "NotoSerif-Regular", 12, FG)
    end

    -- ── Right panel: Hava Durumu ─────────────────────────────────────────────
    local rp_x = 479
    self:_paintBorderRect(bb, rp_x, lp_y, lp_w, lp_h, 1, FG)
    self:_text(bb, "Hava",    rp_x + lp_w/2, lp_y + 15, "NotoSerif-Bold", 11, FG)
    self:_text(bb, "Durumu",  rp_x + lp_w/2, lp_y + 28, "NotoSerif-Bold", 11, FG)
    bb:paintRect(rp_x, lp_y + 40, lp_w, 1, FG)

    local forecast = wx.forecast or {}
    local f_start  = lp_y + 48
    local f_count  = math.min(#forecast, 6)
    local f_step   = f_count > 0 and (lp_h - 50) / f_count or 50
    for i = 1, f_count do
        local fw = forecast[i]
        local fy = f_start + (i-1)*f_step + 8
        local ftemp = (self.unit == "F")
            and string.format("%d°", fw.temp_f or 0)
            or  string.format("%d°", fw.temp_c or 0)
        local ficon = WX_ICON[fw.condition or "cloud"] or "\xE2\x98\x81"
        self:_text(bb, fw.day_tr or "", rp_x + lp_w/2, fy,    "NotoSerif-Bold", 10, FG)
        self:_text(bb, ficon .. " " .. ftemp, rp_x + lp_w/2, fy+14, "NotoSans-Regular", 11, FG)
    end

    -- ── Horizontal rules ─────────────────────────────────────────────────────
    bb:paintRect(40, H-170, 520, 1, FG)
    bb:paintRect(40, H-131, 520, 1, FG)
    bb:paintRect(40, H-75,  520, 1, FG)

    -- ── Tarihte Bugün ────────────────────────────────────────────────────────
    local hist_title = (hist.title or "Tarihte Bugün"):sub(1, 50)
    self:_text(bb, hist_title, 300, H-148, "NotoSerif-Bold", 17, FG)

    -- ── Özlü söz ─────────────────────────────────────────────────────────────
    local qt = '"' .. (quot.text   or ""):sub(1, 55) .. '"'
    local qa = "—" .. (quot.author or "")
    self:_text(bb, qt, 300, H-113, "NotoSerif-Regular", 12, FG)
    self:_text(bb, qa, 300, H- 97, "NotoSerif-Regular", 11, FG)

    -- ── Bottom control bar ───────────────────────────────────────────────────
    local cy = H - 58

    -- ✕ Close
    self:_paintBorderRect(bb, 40, cy - 4, 32, 28, 1, FG)
    self:_text(bb, "\xE2\x9C\x95", 56, cy + 16, "NotoSans-Regular", 16, FG) -- ✕

    -- Battery
    local batt_str = string.format("\xF0\x9F\x94\x8B %%%d", self.battery) -- 🔋
    self:_text(bb, batt_str, 120, cy + 16, "NotoSans-Regular", 13, FG)

    -- °C / °F
    local c_face = Font:getFace("NotoSans-Bold", 15)
    local c_w    = c_face:getSize().w * 2   -- rough width for "°C"
    local cf_x   = 265
    if self.unit == "C" then
        self:_text(bb, "\xC2\xB0C", cf_x,         cy + 16, "NotoSans-Bold", 15, FG)
        bb:paintRect(cf_x - 10, cy + 18, 24, 1, FG)  -- underline C
        self:_text(bb, "\xC2\xB0F", cf_x + 28,    cy + 16, "NotoSans-Bold", 15, FG)
    else
        self:_text(bb, "\xC2\xB0C", cf_x,         cy + 16, "NotoSans-Bold", 15, FG)
        self:_text(bb, "\xC2\xB0F", cf_x + 28,    cy + 16, "NotoSans-Bold", 15, FG)
        bb:paintRect(cf_x + 18, cy + 18, 24, 1, FG)  -- underline F
    end

    -- Brightness icons
    local br_label = BR_LABELS[self.br_index] or "☀"
    self:_text(bb, "○ ☀ " .. br_label, 360, cy + 16, "NotoSans-Regular", 13, FG)

    -- Theme: flashlight (light) / moon (dark)
    local theme_icon = (self.theme == "light")
        and "\xF0\x9F\x94\xA6 \xF0\x9F\x8C\x99"  -- 🔦 🌙
        or  "\xF0\x9F\x8C\x99 \xF0\x9F\x94\xA6"  -- 🌙 🔦 (active first)
    self:_text(bb, theme_icon, 510, cy + 16, "NotoSans-Regular", 14, FG)
end

-- ── Helpers ───────────────────────────────────────────────────────────────────

-- Draw a hollow rectangle border (bsize pixels thick)
function MaarifWidget:_paintBorderRect(bb, x, y, w, h, bsize, color)
    bb:paintRect(x,         y,         w,     bsize, color)  -- top
    bb:paintRect(x,         y+h-bsize, w,     bsize, color)  -- bottom
    bb:paintRect(x,         y,         bsize, h,     color)  -- left
    bb:paintRect(x+w-bsize, y,         bsize, h,     color)  -- right
end

-- Render UTF-8 text centred at (cx, baseline_y)
function MaarifWidget:_text(bb, text, cx, y, font_name, size, color)
    if not text or text == "" then return end
    local face = Font:getFace(font_name, size)
    if not face then
        face = Font:getFace("NotoSans-Regular", size)
    end
    if not face then return end

    local tw = TextWidget:new{
        text    = text,
        face    = face,
        fgcolor = color,
    }
    local tw_size = tw:getSize()
    local x_off   = math.floor(cx - tw_size.w / 2)
    local y_off   = math.floor(y  - tw_size.h)
    tw:paintTo(bb, x_off, y_off)
    tw:free()
end

function MaarifWidget:onCloseWidget()
    UIManager:setDirty(nil, "full")
end

return MaarifWidget
