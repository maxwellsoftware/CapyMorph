-- CapyMorph sync — share your transmog/morph with other CapyMorph users so they
-- render it on their own screen. Client-side only: each viewer applies it locally
-- to your unit via SetUnitVisibleItemID / SetUnitDisplayID. No server effect.
--
-- Wire format (addon message, prefix "CapyMorph"):
--   "C" .. I<slot>,<item>;<slot>,<item>;... [|M<displayID>]   -- config (hidden = item 0)
--   "?"                                                       -- request: everyone resend
--
-- Transport: PARTY / RAID / GUILD addon channels (reliable on TurtleWoW). Applies
-- to any peer we can reference: party/raid members, current target, mouseover.

local PREFIX = "CapyMorph"
local HEARTBEAT = 20      -- resend my config at least this often (s)
local TICK = 3            -- re-apply peers / poll my config this often (s)
local FORCE_EVERY = 6     -- force a re-apply (fights model reloads) this often (s)

local peers = {}          -- name -> { sig, items={slot=item}, model, prevSlots, prevModel, appliedSig }
local mySig = nil
local tAcc, tBeat, tForce = 0, 0, 0

local function syncOn()
  return CapyMorphDB == nil or CapyMorphDB.sync ~= false   -- default ON
end

----------------------------------------------------------------------
-- outgoing
local function dists()
  local d = {}
  if GetNumRaidMembers and GetNumRaidMembers() > 0 then table.insert(d, "RAID")
  elseif GetNumPartyMembers and GetNumPartyMembers() > 0 then table.insert(d, "PARTY") end
  if IsInGuild and IsInGuild() then table.insert(d, "GUILD") end
  return d
end

local function send(text)
  if not SendAddonMessage then return end
  local d = dists(); local i
  for i = 1, table.getn(d) do SendAddonMessage(PREFIX, text, d[i]) end
end

local function broadcast(force)
  if not syncOn() then return end
  local sig = (TMC and TMC.syncSerialize and TMC.syncSerialize()) or ""
  if not force and sig == mySig then return end
  mySig = sig
  send("C" .. sig)
end

----------------------------------------------------------------------
-- incoming + apply
local function parse(s)
  local cfg = { sig = s, items = {} }
  local ipart, mpart
  local bar = string.find(s, "|", 1, true)
  if bar then ipart = string.sub(s, 1, bar - 1); mpart = string.sub(s, bar + 1) else ipart = s end
  if string.sub(ipart, 1, 1) == "I" then
    local pair
    for pair in string.gfind(string.sub(ipart, 2), "([^;]+)") do
      local c = string.find(pair, ",", 1, true)
      if c then
        local slot = tonumber(string.sub(pair, 1, c - 1))
        local item = tonumber(string.sub(pair, c + 1))
        if slot and item then cfg.items[slot] = item end
      end
    end
  end
  if mpart and string.sub(mpart, 1, 1) == "M" then cfg.model = tonumber(string.sub(mpart, 2)) end
  return cfg
end

local function applyTo(token, name, force)
  local cfg = peers[name]
  if not cfg or not UnitExists(token) or not UnitIsPlayer(token) then return end
  if UnitIsUnit and UnitIsUnit(token, "player") then return end
  if not force and cfg.appliedSig == cfg.sig then return end   -- nothing changed; skip (no flicker)
  local newslots = {}
  if SetUnitVisibleItemID then
    local s, i
    for s, i in pairs(cfg.items) do SetUnitVisibleItemID(token, s, i); newslots[s] = true end
    if cfg.prevSlots then
      for s in pairs(cfg.prevSlots) do
        if not newslots[s] then SetUnitVisibleItemID(token, s) end   -- un-morph removed slot
      end
    end
  end
  cfg.prevSlots = newslots
  if SetUnitDisplayID then
    if cfg.model then SetUnitDisplayID(token, cfg.model)
    elseif cfg.prevModel then SetUnitDisplayID(token) end
  end
  cfg.prevModel = cfg.model
  cfg.appliedSig = cfg.sig
end

-- nearby scan: with SuperWoW a nameplate frame's GetName(1) returns the unit GUID,
-- and a GUID works as a unit token. So we can morph any player with a visible
-- nameplate, even ungrouped / untargeted.
local function scanNearby(force)
  if not WorldFrame then return end
  local kids = { WorldFrame:GetChildren() }
  local i
  for i = 1, table.getn(kids) do
    local p = kids[i]
    local guid = p and p.GetName and p:GetName(1)
    if guid and type(guid) == "string" and string.sub(guid, 1, 2) == "0x"
       and UnitExists(guid) and UnitIsPlayer(guid) then
      local nm = UnitName(guid)
      if nm and peers[nm] then applyTo(guid, nm, force) end
    end
  end
end

-- resolve every peer we can currently reference and (re)apply their look
local function reapply(force)
  if not syncOn() then return end
  local toks = { "target", "mouseover" }
  local i
  local np = GetNumPartyMembers and GetNumPartyMembers() or 0
  for i = 1, np do table.insert(toks, "party" .. i) end
  local nr = GetNumRaidMembers and GetNumRaidMembers() or 0
  for i = 1, nr do table.insert(toks, "raid" .. i) end
  for i = 1, table.getn(toks) do
    local tk = toks[i]
    if UnitExists(tk) and UnitIsPlayer(tk) then
      local nm = UnitName(tk)
      if nm and peers[nm] then applyTo(tk, nm, force) end
    end
  end
  scanNearby(force)   -- passive: anyone with a visible nameplate
end

local function onAddonMsg(prefix, message, channel, sender)
  if prefix ~= PREFIX or not message or not sender then return end
  if sender == UnitName("player") then return end
  local tag = string.sub(message, 1, 1)
  if tag == "C" then
    local cfg = parse(string.sub(message, 2))
    local old = peers[sender]
    if old then cfg.prevSlots = old.prevSlots; cfg.prevModel = old.prevModel end  -- keep restore state
    peers[sender] = cfg
    reapply(false)
  elseif tag == "?" then
    broadcast(true)
  end
end

----------------------------------------------------------------------
-- driver
local f = CreateFrame("Frame", "CapyMorphSyncFrame")
f:RegisterEvent("CHAT_MSG_ADDON")
f:RegisterEvent("PLAYER_TARGET_CHANGED")
f:RegisterEvent("UPDATE_MOUSEOVER_UNIT")
f:RegisterEvent("PARTY_MEMBERS_CHANGED")
f:RegisterEvent("RAID_ROSTER_UPDATE")
f:RegisterEvent("PLAYER_ENTERING_WORLD")
f:SetScript("OnEvent", function()
  if event == "CHAT_MSG_ADDON" then onAddonMsg(arg1, arg2, arg3, arg4)
  elseif event == "PLAYER_ENTERING_WORLD" then
    mySig = nil; send("?"); broadcast(true)   -- ask others, announce me
  elseif event == "PARTY_MEMBERS_CHANGED" or event == "RAID_ROSTER_UPDATE" then
    send("?"); broadcast(true); reapply(false)  -- new group: exchange configs now
  else
    reapply(false)
  end
end)
f:SetScript("OnUpdate", function()
  tAcc = tAcc + arg1; tBeat = tBeat + arg1; tForce = tForce + arg1
  if tAcc < TICK then return end
  tAcc = 0
  if not syncOn() then return end
  broadcast(false)                       -- detect & push my own changes
  local force = false
  if tForce >= FORCE_EVERY then tForce = 0; force = true end   -- survive model reloads
  reapply(force)
  if tBeat >= HEARTBEAT then tBeat = 0; broadcast(true) end
end)

-- public toggle (used by /cm sync and the UI)
function TMC.syncSet(on)
  if not CapyMorphDB then return end
  CapyMorphDB.sync = (on and true) or false
  if on then mySig = nil; send("?"); broadcast(true); TMC.msg("transmog sync |cff66cc66ON|r")
  else TMC.msg("transmog sync |cffff5555OFF|r (your look stays; peers keep last seen until relog)") end
end
function TMC.syncState() return syncOn() end
