--[[
  Maarif KOReader Plugin — entry point.
  Registers "Maarif Ekranı" in the main menu and opens the display widget.
--]]

local WidgetContainer = require("ui/widget/container/widgetcontainer")
local UIManager       = require("ui/uimanager")
local NetworkMgr      = require("ui/network/manager")
local InfoMessage      = require("ui/widget/infomessage")
local logger           = require("logger")

local Maarif = WidgetContainer:extend{ name = "maarif" }

function Maarif:init()
    self.ui.menu:registerToMainMenu(self)
end

function Maarif:addToMainMenu(menu_items)
    menu_items.maarif = {
        text     = "Maarif Ekranı",
        sorting_hint = "tools",
        callback = function()
            self:openDisplay()
        end,
    }
end

function Maarif:openDisplay()
    -- Ensure WiFi is on so we can fetch fresh data
    if NetworkMgr:isConnected() then
        self:_launchWidget()
    else
        NetworkMgr:turnOnWifi(function()
            self:_launchWidget()
        end)
    end
end

function Maarif:_launchWidget()
    local ok, MaarifWidget = pcall(require, "maarifwidget")
    if not ok then
        UIManager:show(InfoMessage:new{
            text = "Maarif widget yüklenemedi:\n" .. tostring(MaarifWidget),
        })
        return
    end
    local widget = MaarifWidget:new{}
    UIManager:show(widget)
    UIManager:setDirty(widget, "full")
end

return Maarif
