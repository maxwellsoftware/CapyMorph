-- CapyMorph — in-game transmogrifier-style window.
-- Paper-doll (your character with the current transmog), slot buttons,
-- LMB = pick a look, RMB = remove (confirm). Uses TMC + CapyMorphData.

local ROWS = 18
local ROWH = 18

-- slot: {invSlot, label, icon, side, order}  side: "L" left, "R" right, "B" bottom row
local SLOTS = {
  {1,"Head","Interface\\PaperDoll\\UI-PaperDoll-Slot-Head","L",1},
  {3,"Shoulder","Interface\\PaperDoll\\UI-PaperDoll-Slot-Shoulder","L",2},
  {15,"Back","Interface\\PaperDoll\\UI-PaperDoll-Slot-Chest","L",3},
  {5,"Chest","Interface\\PaperDoll\\UI-PaperDoll-Slot-Chest","L",4},
  {4,"Shirt","Interface\\PaperDoll\\UI-PaperDoll-Slot-Shirt","L",5},
  {19,"Tabard","Interface\\PaperDoll\\UI-PaperDoll-Slot-Tabard","L",6},
  {9,"Wrist","Interface\\PaperDoll\\UI-PaperDoll-Slot-Wrists","L",7},
  {10,"Hands","Interface\\PaperDoll\\UI-PaperDoll-Slot-Hands","R",1},
  {6,"Waist","Interface\\PaperDoll\\UI-PaperDoll-Slot-Waist","R",2},
  {7,"Legs","Interface\\PaperDoll\\UI-PaperDoll-Slot-Legs","R",3},
  {8,"Feet","Interface\\PaperDoll\\UI-PaperDoll-Slot-Feet","R",4},
  {16,"Main Hand","Interface\\PaperDoll\\UI-PaperDoll-Slot-MainHand","B",1},
  {17,"Off Hand","Interface\\PaperDoll\\UI-PaperDoll-Slot-SecondaryHand","B",2},
  {18,"Ranged","Interface\\PaperDoll\\UI-PaperDoll-Slot-Ranged","B",3},
}
local FORMORDER = {"bear","cat","moonkin"}
local FORMLABEL = {bear="Bear Form", cat="Cat Form", moonkin="Moonkin Form"}

local UI = {tab="armory", slot=16, form="cat", filtered={}, selected=nil}
local pickName  -- forward-declared: referenced by the form buttons created below

----------------------------------------------------------------------
local sw, sh = GetScreenWidth(), GetScreenHeight()
local W = math.min(880, sw*0.7); if W < 760 then W = math.min(760, sw*0.95) end
local H = math.min(640, sh*0.7); if H < 520 then H = math.min(520, sh*0.95) end

local f = CreateFrame("Frame", "CapyMorphFrame", UIParent)
f:SetWidth(W); f:SetHeight(H); f:SetPoint("CENTER", 0, 0)
f:SetScale(1.2)  -- 20% larger, proportions preserved
f:SetBackdrop({ bgFile="Interface\\DialogFrame\\UI-DialogBox-Background",
  edgeFile="Interface\\DialogFrame\\UI-DialogBox-Border", tile=true, tileSize=32, edgeSize=32,
  insets={left=11,right=12,top=12,bottom=11} })
f:SetMovable(true); f:EnableMouse(true); f:RegisterForDrag("LeftButton")
f:SetScript("OnDragStart", function() f:StartMoving() end)
f:SetScript("OnDragStop", function() f:StopMovingOrSizing() end)
f:SetScript("OnHide", function() if TMC and TMC.previewClear then TMC.previewClear() end end)
f:SetFrameStrata("HIGH"); f:Hide()

local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOP", 0, -16); title:SetText("CapyMorph")
local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
close:SetPoint("TOPRIGHT", -8, -8)

-- tabs (centered on the window, order: Armory / Character / Druid / Presets)
local tabBtns = {}
-- "Mounts" tab is hidden until the mount-morph mechanism is finished (WIP).
local TABDEF = {{"Armory","armory"},{"My Character","character"},{"Druid Forms","druid"},{"Presets","presets"}}
local TW, TGAP = 120, 8
local ntab = table.getn(TABDEF)
local totalw = ntab*TW + (ntab-1)*TGAP
for i=1, ntab do
  local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  b:SetWidth(TW); b:SetHeight(26)
  b:SetPoint("TOP", f, "TOP", -totalw/2 + TW/2 + (i-1)*(TW+TGAP), -42)
  b:SetText(TABDEF[i][1])
  local key = TABDEF[i][2]
  b:SetScript("OnClick", function() UI.setTab(key) end)
  tabBtns[key] = b
end

local MODEL_X, MODEL_Y, MODEL_W, MODEL_H = 70, -118, 250, H-244
local PICK_X = MODEL_X + MODEL_W + 10 + 40 + 30  -- right of the right-hand slot column + gap = 400
local MROWS = ROWS                               -- Mounts tab: full-height "your mounts" list
-- Mounts tab 3-column layout: [ your mounts | full preview | narrow search ]
local ML_X, ML_W = 16, 168                       -- left column: mounts list
local MP_W = 190                                 -- right column: narrow search/database (~2.3x narrower)
local MP_X = W - MP_W - 24                        -- right column left edge
local MC_X = ML_X + ML_W + 24                     -- centre preview x
local MC_W = math.max(220, MP_X - MC_X - 28)      -- centre preview width (fills the gap)

----------------------------------------------------------------------
-- character / preview model — DOUBLE-BUFFERED.
-- The new look loads into the hidden (alpha 0) buffer and we reveal it only
-- after it has had time to load, so the white default model never flashes.
-- The previously shown preview stays visible until the swap.
local facing = 0.5
local swapT = nil
local modelA, modelB, front, back

local function mkModel(name)
  local m = CreateFrame("DressUpModel", name, f)
  m:SetWidth(MODEL_W); m:SetHeight(MODEL_H); m:SetPoint("TOPLEFT", MODEL_X, MODEL_Y)
  m:SetBackdrop({ bgFile="Interface\\DialogFrame\\UI-DialogBox-Background", tile=true, tileSize=16,
    edgeFile="Interface\\Tooltips\\UI-Tooltip-Border", edgeSize=12, insets={left=4,right=4,top=4,bottom=4} })
  m:EnableMouse(true)
  m:SetScript("OnMouseDown", function() this.dragging=true; this.dragX=GetCursorPosition(); this.dragF=facing end)
  m:SetScript("OnMouseUp", function() this.dragging=false end)
  m:SetScript("OnHide", function() this.dragging=false end)
  return m
end
local function bringFront(m) m:SetAlpha(1); m:SetFrameLevel(f:GetFrameLevel()+3) end
local function sendBack(m)  m:SetAlpha(0); m:SetFrameLevel(f:GetFrameLevel()+2) end

modelA = mkModel("CapyMorphModel")
modelB = mkModel("CapyMorphModelB")
front, back = modelA, modelB
bringFront(modelA); sendBack(modelB)

local function loadUnit(m)
  if m.mode == "creature" and m.ClearModel then m:ClearModel() end
  m.mode = "unit"
  if m.SetUnit then m:SetUnit("player") end
  if m.SetFacing then m:SetFacing(facing) end
  m.refreshN = 2; m.refreshT = 0.12   -- nudge the (hidden) load a couple times
end
local function loadCreature(m, path, did)
  m.refreshN = nil
  if m.ClearModel then m:ClearModel() end
  m.mode = "creature"
  if path and path ~= "" then m:SetModel(path)
  elseif did and m.SetDisplayInfo then m:SetDisplayInfo(did) end
  if m.SetModelScale then m:SetModelScale(1) end
  if m.SetPosition then m:SetPosition(0,0,0) end
  if m.SetFacing then m:SetFacing(facing) end
end

local function present() swapT = 0.45 end   -- reveal the loaded buffer shortly
local function doSwap()
  swapT = nil
  bringFront(back); sendBack(front)
  front, back = back, front
end

local function eachUpdate(m)
  if m.dragging then
    local x = GetCursorPosition(); facing = m.dragF + (x - m.dragX)*0.012
    modelA:SetFacing(facing); modelB:SetFacing(facing)
  end
  if m.refreshN and m.refreshN > 0 and m.mode == "unit" and m.SetUnit and not m.dragging then
    m.refreshT = (m.refreshT or 0.12) - arg1
    if m.refreshT <= 0 then
      m.refreshT = 0.12; m.refreshN = m.refreshN - 1
      m:SetUnit("player"); if m.SetFacing then m:SetFacing(facing) end
    end
  end
end
modelA:SetScript("OnUpdate", function()
  eachUpdate(modelA)
  if swapT then swapT = swapT - arg1; if swapT <= 0 then doSwap() end end
end)
modelB:SetScript("OnUpdate", function() eachUpdate(modelB) end)

-- public preview entry points (load into the hidden buffer, then swap)
local function dollShow() loadUnit(back); present() end
local function previewCreature(path, did) loadCreature(back, path, did); present() end
local function showPlayer() dollShow() end

-- show what the character currently looks like for the active tab
local function showCurrent()
  if UI.tab == "armory" then dollShow()
  elseif UI.tab == "character" then
    local p = TMC.modelPath()
    if p then previewCreature(p, TMC.db().model) else showPlayer() end
  elseif UI.tab == "druid" then
    local mode = TMC.formMode(UI.form)
    if mode == "model" then previewCreature(TMC.formPath(UI.form), TMC.formDisplay(UI.form))
    else showPlayer() end  -- "self" or unchanged: show the character
  elseif UI.tab == "presets" then
    local nm = UI.selected and UI.selected[1]
    local pr = nm and TMC.getPreset(nm)
    if pr and (pr.modelPath or pr.model) then previewCreature(pr.modelPath, pr.model)
    elseif pr and pr.items then TMC.previewSet(nil, pr.items); dollShow()
    else showPlayer() end
  end
end

----------------------------------------------------------------------
-- paper-doll slot buttons (Armory)
StaticPopupDialogs["CAPYMORPH_REMOVE"] = {
  text = "Remove transmog from this slot?", button1 = YES, button2 = NO,
  OnAccept = function() TMC.setItem(UI._rmSlot, nil); TMC.previewClear(); UI.refreshSlots(); dollShow() end,
  timeout = 0, whileDead = 1, hideOnEscape = 1,
}

local SLOTSZ = 40
local slotBtns = {}
local function makeSlot(s)
  local b = CreateFrame("Button", nil, f)
  b:SetWidth(SLOTSZ); b:SetHeight(SLOTSZ)
  b:SetFrameLevel(f:GetFrameLevel()+8)   -- above the preview model so slot labels draw on top
  if s[4]=="L" then
    b:SetPoint("TOPLEFT", 16, MODEL_Y - (s[5]-1)*(SLOTSZ+8))
  elseif s[4]=="R" then
    b:SetPoint("TOPLEFT", MODEL_X+MODEL_W+10, MODEL_Y - (s[5]-1)*(SLOTSZ+8))
  else -- bottom row, horizontally centered under the model
    local roww = 3*SLOTSZ + 2*10
    local startx = MODEL_X + (MODEL_W - roww)/2
    b:SetPoint("TOPLEFT", startx + (s[5]-1)*(SLOTSZ+10), MODEL_Y - MODEL_H - 14)
  end
  -- visible slot frame
  b:SetBackdrop({ bgFile="Interface\\Buttons\\UI-EmptySlot", edgeFile="Interface\\Tooltips\\UI-Tooltip-Border", edgeSize=12, insets={left=3,right=3,top=3,bottom=3} })
  b:SetBackdropColor(0.55,0.55,0.55,1)
  local ic = b:CreateTexture(nil,"ARTWORK"); ic:SetPoint("TOPLEFT",4,-4); ic:SetPoint("BOTTOMRIGHT",-4,4)
  ic:SetTexture(s[3]); ic:SetBlendMode("ADD"); ic:SetVertexColor(3.0,3.0,3.0)  -- overbright + additive so the dim slot icons are clearly visible
  b.ic=ic
  local br = b:CreateTexture(nil,"OVERLAY"); br:SetPoint("TOPLEFT",-3,3); br:SetPoint("BOTTOMRIGHT",3,-3)
  br:SetTexture("Interface\\Buttons\\UI-ActionButton-Border"); br:SetBlendMode("ADD"); br:SetVertexColor(0.2,1,0.2); br:Hide(); b.border=br
  local lbl = b:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall")
  if s[4]=="L" then lbl:SetPoint("LEFT", b, "RIGHT", 4, 0); lbl:SetJustifyH("LEFT")
  elseif s[4]=="R" then lbl:SetPoint("RIGHT", b, "LEFT", -4, 0); lbl:SetJustifyH("RIGHT")
  else lbl:SetPoint("TOP", b, "BOTTOM", 0, -2); lbl:SetJustifyH("CENTER") end
  lbl:SetWidth(0); b.lbl=lbl
  b.slot=s[1]; b.label=s[2]
  b:RegisterForClicks("LeftButtonUp","RightButtonUp")
  b:SetScript("OnClick", function()
    if arg1=="RightButton" then
      local db=TMC.db()
      if db and db.items and db.items[b.slot] then UI._rmSlot=b.slot; StaticPopup_Show("CAPYMORPH_REMOVE") end
    else UI.selectSlot(b.slot) end
  end)
  b:SetScript("OnEnter", function() GameTooltip:SetOwner(b,"ANCHOR_RIGHT"); GameTooltip:SetText(b.label); local db=TMC.db(); local nm = db and db.items and db.items[b.slot] and TMC.itemLabel(b.slot); if nm then GameTooltip:AddLine(nm,1,1,1) end; GameTooltip:AddLine("Left-click: choose | Right-click: remove",0.6,0.6,0.6); GameTooltip:Show() end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  -- mini Hide/Show button: a strip across the bottom of the slot
  local hb = CreateFrame("Button", nil, b)
  hb:SetWidth(SLOTSZ-4); hb:SetHeight(13); hb:SetPoint("BOTTOM", b, "BOTTOM", 0, 3)
  hb:SetFrameLevel(b:GetFrameLevel()+5)
  local hbg = hb:CreateTexture(nil,"BACKGROUND"); hbg:SetAllPoints(hb); hbg:SetTexture(0,0,0,0.65); hb.bg=hbg
  local hbt = hb:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall"); hbt:SetPoint("CENTER",0,0); hbt:SetText("Hide")
  hb.txt = hbt; b.hide = hb
  hb:SetScript("OnClick", function() TMC.previewClear(); TMC.toggleHide(b.slot); UI.refreshSlots(); dollShow() end)
  hb:SetScript("OnEnter", function() hbg:SetTexture(0.25,0.25,0.25,0.85); GameTooltip:SetOwner(hb,"ANCHOR_RIGHT"); GameTooltip:SetText(TMC.isHidden(b.slot) and "Show this slot" or "Hide this slot entirely"); GameTooltip:Show() end)
  hb:SetScript("OnLeave", function() hbg:SetTexture(0,0,0,0.65); GameTooltip:Hide() end)
  slotBtns[s[1]] = b
end
for _, s in ipairs(SLOTS) do makeSlot(s) end

function UI.refreshSlots()
  local db = TMC.db()
  local k, b
  for k, b in pairs(slotBtns) do
    local hidden = TMC.isHidden(b.slot)
    local trans = db and db.items and db.items[b.slot]
    if hidden then b.border:Show(); b.border:SetVertexColor(1,0.4,0.4); b.lbl:SetText(trans and "|cffff6666hidden|r |cff888888("..(TMC.itemLabel(b.slot) or "transmog")..")|r" or "|cffff6666hidden|r")
    elseif trans then b.border:Show(); b.border:SetVertexColor(0.2,1,0.2); b.lbl:SetText(TMC.itemLabel(b.slot) or "transmogged")
    else b.border:Hide(); b.lbl:SetText("") end
    if b.hide then
      b.hide.txt:SetText(hidden and "Show" or "Hide")
      b.hide.txt:SetTextColor(hidden and 1 or 0.9, hidden and 0.5 or 0.9, hidden and 0.5 or 0.9)
    end
    if b.slot == UI.slot and UI.tab=="armory" then b:LockHighlight() else b:UnlockHighlight() end
  end
end

----------------------------------------------------------------------
-- form selector (Druid): three buttons + "show my character" + status line,
-- in the band above the model. Pick which form you are editing, then choose a
-- creature from the list on the right and Apply (or "Show my character").
local FBW = 88
local formBtns = {}
for i, key in ipairs(FORMORDER) do
  local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
  b:SetWidth(FBW); b:SetHeight(24); b:SetPoint("TOPLEFT", 16 + (i-1)*(FBW+6), -76)
  b:SetText(FORMLABEL[key])
  local k2 = key
  b:SetScript("OnClick", function() UI.form=k2; UI.selected=nil; pickName:SetText(""); UI.refreshForms(); UI.rebuild(); showCurrent() end)
  formBtns[key] = b
end
local selfBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
selfBtn:SetWidth(160); selfBtn:SetHeight(24); selfBtn:SetPoint("TOPLEFT", 16 + 3*(FBW+6) + 12, -76)
selfBtn:SetText("Show my character")
selfBtn:SetScript("OnClick", function() TMC.setForm(UI.form,"self"); UI.refreshForms(); showCurrent(); TMC.msg(UI.form.." -> your character (shapeshift to see it)") end)
local formStatus = f:CreateFontString(nil,"OVERLAY","GameFontNormal")
formStatus:SetPoint("TOPLEFT", 18, -104); formStatus:SetJustifyH("LEFT"); formStatus:SetWidth(W-40)

function UI.refreshForms()
  local k,b
  for k,b in pairs(formBtns) do
    if k==UI.form then b:LockHighlight() else b:UnlockHighlight() end
    local fs = b.GetFontString and b:GetFontString()
    if fs then if k==UI.form then fs:SetTextColor(1,0.82,0) else fs:SetTextColor(1,1,1) end end
  end
  local mode = TMC.formMode(UI.form)
  local txt
  if mode=="model" then txt=(TMC.formLabel(UI.form) or "custom model")
  elseif mode=="self" then txt="my character"
  else txt="normal form (not changed)" end
  if formStatus then formStatus:SetText("Editing "..(FORMLABEL[UI.form] or UI.form)..":  |cffffd100"..txt.."|r") end
end

----------------------------------------------------------------------
-- picker (search + list)
local search = CreateFrame("EditBox", "CapyMorphSearch", f, "InputBoxTemplate")
search:SetWidth(W-PICK_X-130); search:SetHeight(22); search:SetPoint("TOPLEFT", PICK_X+50, MODEL_Y)
search:SetAutoFocus(false)
search:SetScript("OnTextChanged", function() UI.rebuild() end)
local sl = f:CreateFontString(nil,"OVERLAY","GameFontNormal"); sl:SetPoint("RIGHT",search,"LEFT",-6,0); sl:SetText("Search:")

local scroll = CreateFrame("ScrollFrame", "CapyMorphScroll", f, "FauxScrollFrameTemplate")
scroll:SetWidth(W-PICK_X-60); scroll:SetHeight(ROWS*ROWH); scroll:SetPoint("TOPLEFT", PICK_X, MODEL_Y-32)
scroll:SetScript("OnVerticalScroll", function() FauxScrollFrame_OnVerticalScroll(ROWH, UI.update) end)
local rows = {}
for i=1, ROWS do
  local b = CreateFrame("Button", nil, f)
  b:SetWidth(W-PICK_X-72); b:SetHeight(ROWH); b:SetPoint("TOPLEFT", scroll, "TOPLEFT", 0, -((i-1)*ROWH))
  local fs=b:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall"); fs:SetPoint("LEFT",2,0); fs:SetJustifyH("LEFT"); b.fs=fs
  local hl=b:CreateTexture(nil,"BACKGROUND"); hl:SetAllPoints(b); hl:SetTexture(0.3,0.5,0.9,0.4); hl:Hide(); b.hl=hl
  b:SetScript("OnClick", function() UI.selectIndex(b.dataIndex) end)
  rows[i]=b
end

local applyBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
applyBtn:SetWidth(160); applyBtn:SetHeight(30); applyBtn:SetPoint("BOTTOMRIGHT", -20, 16)
applyBtn:SetText("Apply")
applyBtn:SetScript("OnClick", function() UI.apply() end)
pickName = f:CreateFontString(nil,"OVERLAY","GameFontNormal")
pickName:SetPoint("BOTTOMLEFT", PICK_X, 56); pickName:SetWidth(W-PICK_X-200); pickName:SetJustifyH("LEFT"); pickName:SetText("")

-- per-section reset, under the preview (My Character / Druid only)
local resetBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
resetBtn:SetWidth(MODEL_W); resetBtn:SetHeight(24)
resetBtn:SetPoint("TOPLEFT", MODEL_X, MODEL_Y - MODEL_H - 14)
resetBtn:SetText("Remove this morph")
resetBtn:SetScript("OnClick", function()
  UI.selected=nil; pickName:SetText("")
  if UI.tab=="character" then TMC.clearBody(); showCurrent(); TMC.msg("character morph removed")
  elseif UI.tab=="druid" then TMC.setForm(UI.form,"off"); UI.refreshForms(); showCurrent(); TMC.msg(UI.form.." reset to normal")
  elseif UI.tab=="mounts" then
    if UI.mount then TMC.resetMount(UI.mount.display); previewCreature(nil, UI.mount.display); UI.mountUpdate(); TMC.msg(UI.mount.name.." restored to its original model")
    else TMC.msg("pick one of your mounts on the left first") end
  end
  UI.update()
end)
resetBtn:Hide()

----------------------------------------------------------------------
-- Mounts tab — left column: "your mounts" list (scanned from the Companions/
-- mounts spellbook tab, matched to CapyMorphData.mounts). Full height, left side.
local mLabel = f:CreateFontString(nil,"OVERLAY","GameFontNormal")
mLabel:SetPoint("TOPLEFT", ML_X, MODEL_Y-6); mLabel:SetText("Your mounts:"); mLabel:Hide()
local mScroll = CreateFrame("ScrollFrame", "CapyMorphMScroll", f, "FauxScrollFrameTemplate")
mScroll:SetWidth(ML_W); mScroll:SetHeight(MROWS*ROWH)
mScroll:SetPoint("TOPLEFT", ML_X, MODEL_Y-32)
mScroll:SetScript("OnVerticalScroll", function() FauxScrollFrame_OnVerticalScroll(ROWH, UI.mountUpdate) end)
local mRows = {}
for i=1, MROWS do
  local b = CreateFrame("Button", nil, f)
  b:SetWidth(ML_W-12); b:SetHeight(ROWH); b:SetPoint("TOPLEFT", mScroll, "TOPLEFT", 0, -((i-1)*ROWH))
  local fs=b:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall"); fs:SetPoint("LEFT",2,0); fs:SetJustifyH("LEFT"); b.fs=fs
  local hl=b:CreateTexture(nil,"BACKGROUND"); hl:SetAllPoints(b); hl:SetTexture(0.3,0.5,0.9,0.4); hl:Hide(); b.hl=hl
  b:SetScript("OnClick", function() UI.selectMount(b.mIndex) end)
  mRows[i]=b; b:Hide()
end
mScroll:Hide()

----------------------------------------------------------------------
-- bottom-left: name input + Save (saves the CURRENT look as a preset).
-- Loading / deleting existing presets is done in the Presets tab.
local presetBox = CreateFrame("EditBox", "CapyMorphPreset", f, "InputBoxTemplate")
presetBox:SetWidth(130); presetBox:SetHeight(20); presetBox:SetPoint("BOTTOMLEFT", 78, 18); presetBox:SetAutoFocus(false)
local pl = f:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall"); pl:SetPoint("RIGHT",presetBox,"LEFT",-4,0); pl:SetText("Preset:")
local saveBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate"); saveBtn:SetWidth(60); saveBtn:SetHeight(20); saveBtn:SetPoint("LEFT",presetBox,"RIGHT",6,0); saveBtn:SetText("Save")
saveBtn:SetScript("OnClick", function() local nm=presetBox:GetText(); if nm and nm~="" then TMC.savePreset(nm); if UI.tab=="presets" then UI.rebuild() end else TMC.msg("type a preset name first") end end)

-- Clear all (confirmed) — bottom-right, left of Apply, in every tab
StaticPopupDialogs["CAPYMORPH_CLEARALL"] = {
  text = "Remove ALL morphs (items, forms, body, hidden)?", button1 = YES, button2 = NO,
  OnAccept = function() TMC.clear(); UI.refreshSlots(); if UI.refreshForms then UI.refreshForms() end; showCurrent() end,
  timeout = 0, whileDead = 1, hideOnEscape = 1,
}
local clearBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate"); clearBtn:SetWidth(90); clearBtn:SetHeight(24); clearBtn:SetPoint("RIGHT", applyBtn, "LEFT", -8, 0); clearBtn:SetText("Clear all")
clearBtn:SetScript("OnClick", function() StaticPopup_Show("CAPYMORPH_CLEARALL") end)

-- Delete preset (confirmed) — Presets tab only, deletes the selected preset
StaticPopupDialogs["CAPYMORPH_DELPRESET"] = {
  text = "Delete preset \"%s\"?", button1 = YES, button2 = NO,
  OnAccept = function() TMC.deletePreset(UI._delPreset); UI.selected=nil; pickName:SetText(""); presetBox:SetText(""); UI.rebuild() end,
  timeout = 0, whileDead = 1, hideOnEscape = 1,
}
local delBtn = CreateFrame("Button", nil, f, "UIPanelButtonTemplate"); delBtn:SetWidth(110); delBtn:SetHeight(24); delBtn:SetPoint("RIGHT", clearBtn, "LEFT", -8, 0); delBtn:SetText("Delete preset")
delBtn:SetScript("OnClick", function()
  local nm = (UI.selected and UI.selected[1]) or presetBox:GetText()
  if nm and nm ~= "" and TMC.getPreset(nm) then UI._delPreset = nm; StaticPopup_Show("CAPYMORPH_DELPRESET", nm)
  else TMC.msg("select a preset in the list to delete") end
end)
delBtn:Hide()

----------------------------------------------------------------------
local function source()
  if UI.tab=="armory" then return (CapyMorphData and CapyMorphData.items and CapyMorphData.items[UI.slot]) or {} end
  if UI.tab=="presets" then
    local t, names = {}, TMC.presetNames()
    local i for i=1, table.getn(names) do t[i] = {names[i]} end
    return t
  end
  return (CapyMorphData and CapyMorphData.creatures) or {}
end

function UI.rebuild()
  local q = string.lower(search:GetText() or ""); local src=source(); UI.filtered={}
  local i
  for i=1, table.getn(src) do
    local e=src[i]
    if q=="" or string.find(string.lower(e[1]), q, 1, true) then table.insert(UI.filtered, e) end
    if table.getn(UI.filtered) >= 2000 then break end
  end
  UI.update()
end

function UI.update()
  local n=table.getn(UI.filtered)
  FauxScrollFrame_Update(scroll, n, ROWS, ROWH)
  local off=FauxScrollFrame_GetOffset(scroll)
  local i
  for i=1, ROWS do
    local idx=off+i; local b=rows[i]
    if idx<=n then b.dataIndex=idx; b.fs:SetText(UI.filtered[idx][1]); if UI.selected==UI.filtered[idx] then b.hl:Show() else b.hl:Hide() end; b:Show()
    else b:Hide() end
  end
end

function UI.selectIndex(idx)
  local e=UI.filtered[idx]; if not e then return end
  UI.selected=e; pickName:SetText(e[1])
  if UI.tab=="armory" then TMC.preview(UI.slot, e[2], nil); dollShow()   -- live, local, reversible
  elseif UI.tab=="presets" then presetBox:SetText(e[1]); showCurrent()
  else previewCreature(e[3], e[2]) end                                    -- creature/form: floating model
  UI.update()
end

function UI.selectSlot(slot)
  TMC.previewClear(); UI.slot=slot; UI.selected=nil; search:SetText(""); UI.refreshSlots(); UI.rebuild(); dollShow()
end

function UI.apply()
  local e=UI.selected; if not e then TMC.msg("pick something from the list"); return end
  if UI.tab=="armory" then TMC.setItem(UI.slot, e[2], e[1]); TMC.previewClear(); UI.refreshSlots(); dollShow(); TMC.msg("applied: "..e[1])
  elseif UI.tab=="druid" then
    TMC.setForm(UI.form, e[2], e[1], e[3]); UI.refreshForms(); showCurrent()
    local cur = TMC.activeForm()
    if cur == UI.form then TMC.msg(UI.form.." = "..e[1]..": applied now (you are in "..cur..")")
    else TMC.msg(UI.form.." = "..e[1]..". |cffff8800detect: "..TMC.formDebug().."|r") end
  elseif UI.tab=="presets" then TMC.loadPreset(e[1]); TMC.previewClear(); UI.refreshSlots(); TMC.msg("loaded preset "..e[1])
  elseif UI.tab=="mounts" then
    if not UI.mount then TMC.msg("pick one of your mounts on the left first"); return end
    TMC.setMount(UI.mount.display, e[2], UI.mount.name, e[1]); UI.mountUpdate(); TMC.msg(UI.mount.name.." -> "..e[1])
  else TMC.setBody(e[2], e[1], e[3]); showCurrent(); TMC.msg("you are now: "..e[1]) end
end

-- Mounts tab: scan the Companions spellbook tab and keep the ones we recognise.
function UI.scanMounts()
  UI.playerMounts = {}
  local md = CapyMorphData and CapyMorphData.mounts
  if not md then return end
  local nt = (GetNumSpellTabs and GetNumSpellTabs()) or 0
  local ti
  for ti=1, nt do
    local name, _, off, num = GetSpellTabInfo(ti)
    local lname = string.lower(name or "")
    if name and (string.find(lname, "mount", 1, true) or string.find(lname, "companion", 1, true)) then
      local s
      for s=(off or 0)+1, (off or 0)+(num or 0) do
        local sp = GetSpellName(s, BOOKTYPE_SPELL)
        if sp and md[sp] then table.insert(UI.playerMounts, {sp, md[sp]}) end
      end
    end
  end
  table.sort(UI.playerMounts, function(a,b) return a[1] < b[1] end)
end

function UI.mountUpdate()
  local n = table.getn(UI.playerMounts or {})
  FauxScrollFrame_Update(mScroll, n, MROWS, ROWH)
  local off = FauxScrollFrame_GetOffset(mScroll)
  local i
  for i=1, MROWS do
    local idx=off+i; local b=mRows[i]
    if idx<=n then
      local e=UI.playerMounts[idx]; b.mIndex=idx
      local ov = TMC.mountMorph(e[2])
      b.fs:SetText(e[1]..((ov and ov.toName) and (" |cff66cc66> "..ov.toName.."|r") or ""))
      if UI.mount and UI.mount.display==e[2] then b.hl:Show() else b.hl:Hide() end
      b:Show()
    else b:Hide() end
  end
end

function UI.selectMount(idx)
  local e = UI.playerMounts and UI.playerMounts[idx]; if not e then return end
  UI.mount = {name=e[1], display=e[2]}; UI.selected=nil
  pickName:SetText("morph |cffffd100"..e[1].."|r into...")
  local ov = TMC.mountMorph(e[2])
  previewCreature(nil, (ov and ov.to) or e[2])   -- show its current (or already-overridden) model
  UI.mountUpdate(); UI.update()
end

function UI.setTab(key)
  TMC.previewClear(); UI.tab=key
  local k for k in pairs(tabBtns) do if k==key then tabBtns[k]:LockHighlight() else tabBtns[k]:UnlockHighlight() end end
  local armory = (key=="armory")
  local k2,b2 for k2,b2 in pairs(slotBtns) do if armory then b2:Show() else b2:Hide() end end
  local druid = (key=="druid")
  local fk,fb for fk,fb in pairs(formBtns) do if druid then fb:Show() else fb:Hide() end end
  if druid then selfBtn:Show(); formStatus:Show(); UI.refreshForms() else selfBtn:Hide(); formStatus:Hide() end
  local mounts = (key=="mounts")
  -- Mounts tab = 3 columns: [ your mounts | full preview | narrow search ].
  -- Re-anchor the shared preview + picker for this tab, restore them otherwise.
  modelA:ClearAllPoints(); modelB:ClearAllPoints()
  search:ClearAllPoints(); scroll:ClearAllPoints()
  local mi
  if mounts then
    modelA:SetWidth(MC_W); modelA:SetHeight(MODEL_H); modelA:SetPoint("TOPLEFT", MC_X, MODEL_Y)
    modelB:SetWidth(MC_W); modelB:SetHeight(MODEL_H); modelB:SetPoint("TOPLEFT", MC_X, MODEL_Y)
    search:SetWidth(MP_W-46); search:SetPoint("TOPLEFT", MP_X+46, MODEL_Y)
    scroll:SetWidth(MP_W); scroll:SetPoint("TOPLEFT", MP_X, MODEL_Y-32)
    for mi=1,ROWS do rows[mi]:SetWidth(MP_W-12) end
    mLabel:Show(); mScroll:Show(); UI.mount=nil; UI.scanMounts(); UI.mountUpdate()
  else
    modelA:SetWidth(MODEL_W); modelA:SetHeight(MODEL_H); modelA:SetPoint("TOPLEFT", MODEL_X, MODEL_Y)
    modelB:SetWidth(MODEL_W); modelB:SetHeight(MODEL_H); modelB:SetPoint("TOPLEFT", MODEL_X, MODEL_Y)
    search:SetWidth(W-PICK_X-130); search:SetPoint("TOPLEFT", PICK_X+50, MODEL_Y)
    scroll:SetWidth(W-PICK_X-60); scroll:SetPoint("TOPLEFT", PICK_X, MODEL_Y-32)
    for mi=1,ROWS do rows[mi]:SetWidth(W-PICK_X-72) end
    mLabel:Hide(); mScroll:Hide(); for mi=1,MROWS do mRows[mi]:Hide() end
  end
  resetBtn:ClearAllPoints()
  if key=="character" or druid then
    resetBtn:SetWidth(MODEL_W); resetBtn:SetPoint("TOPLEFT", MODEL_X, MODEL_Y - MODEL_H - 14)
    resetBtn:Show(); resetBtn:SetText(druid and "Reset this form" or "Remove this morph")
  elseif mounts then
    resetBtn:SetWidth(MC_W); resetBtn:SetPoint("TOPLEFT", MC_X, MODEL_Y - MODEL_H - 14)
    resetBtn:Show(); resetBtn:SetText("Restore original model")
  else resetBtn:Hide() end
  if key=="presets" then delBtn:Show() else delBtn:Hide() end
  pickName:ClearAllPoints()
  if mounts then pickName:SetPoint("BOTTOMLEFT", MC_X, 56); pickName:SetWidth(MC_W)
  else pickName:SetPoint("BOTTOMLEFT", PICK_X, 56); pickName:SetWidth(W-PICK_X-200) end
  search:SetText(""); UI.selected=nil
  if mounts then pickName:SetText("pick a mount on the left") else pickName:SetText("") end
  applyBtn:SetText(key=="presets" and "Load preset" or "Apply")
  UI.rebuild()
  if armory then UI.refreshSlots(); UI.selectSlot(UI.slot or 16)
  elseif mounts then previewCreature(nil, nil)
  else showCurrent() end
end

----------------------------------------------------------------------
-- resize grip (bottom-right): uniform SCALE, so all proportions are preserved.
-- Drag right/left to grow/shrink; the scale is saved per character.
local MIN_SCALE, MAX_SCALE = 0.7, 2.0
local grip = CreateFrame("Button", nil, f)
grip:SetWidth(18); grip:SetHeight(18); grip:SetPoint("BOTTOMRIGHT", -3, 3)
grip:SetFrameLevel(f:GetFrameLevel() + 20)
grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
grip:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
grip:SetScript("OnMouseDown", function() grip.drag = true; grip.cx = GetCursorPosition(); grip.s0 = f:GetScale() end)
grip:SetScript("OnMouseUp", function() grip.drag = false; if CapyMorphDB then CapyMorphDB.uiScale = f:GetScale() end end)
grip:SetScript("OnUpdate", function()
  if not grip.drag then return end
  local x = GetCursorPosition()
  local sc = grip.s0 + (x - grip.cx) * 0.0015
  if sc < MIN_SCALE then sc = MIN_SCALE elseif sc > MAX_SCALE then sc = MAX_SCALE end
  f:SetScale(sc)
end)

function CapyMorphUI_Toggle()
  if f:IsShown() then f:Hide() else
    if CapyMorphDB and CapyMorphDB.uiScale then f:SetScale(CapyMorphDB.uiScale) end  -- restore saved size
    f:Show(); UI.setTab("armory")   -- always open on Armory
  end
end

----------------------------------------------------------------------
-- minimap button (self-contained, no external libs). Click opens the window;
-- drag moves it around the minimap edge; the angle is saved per character.
local mmb = CreateFrame("Button", "CapyMorphMinimapButton", Minimap)
mmb:SetWidth(31); mmb:SetHeight(31)
mmb:SetFrameStrata("MEDIUM"); mmb:SetFrameLevel(8)
mmb:RegisterForClicks("LeftButtonUp", "RightButtonUp")
mmb:RegisterForDrag("LeftButton")

local mmIcon = mmb:CreateTexture(nil, "BACKGROUND")
mmIcon:SetWidth(20); mmIcon:SetHeight(20)
mmIcon:SetTexture("Interface\\Icons\\Spell_Nature_Polymorph")
mmIcon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
mmIcon:SetPoint("CENTER", mmb, "CENTER", 0, 1)

local mmBorder = mmb:CreateTexture(nil, "OVERLAY")
mmBorder:SetWidth(53); mmBorder:SetHeight(53)
mmBorder:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
mmBorder:SetPoint("TOPLEFT", mmb, "TOPLEFT", 0, 0)

local function mmPos(angle)
  local a = math.rad(angle or 200)
  mmb:ClearAllPoints()
  mmb:SetPoint("CENTER", Minimap, "CENTER", 80*math.cos(a), 80*math.sin(a))
end
local function mmDrag()
  local mx, my = Minimap:GetCenter()
  local scale = Minimap:GetEffectiveScale()
  local cx, cy = GetCursorPosition()
  cx = cx/scale; cy = cy/scale
  local angle = math.deg(math.atan2(cy - my, cx - mx))
  TMC.db().minimapAngle = angle
  mmPos(angle)
end
mmb:SetScript("OnClick", function() if CapyMorphUI_Toggle then CapyMorphUI_Toggle() end end)
mmb:SetScript("OnDragStart", function() mmb:SetScript("OnUpdate", mmDrag) end)
mmb:SetScript("OnDragStop", function() mmb:SetScript("OnUpdate", nil) end)
mmb:SetScript("OnEnter", function()
  GameTooltip:SetOwner(mmb, "ANCHOR_LEFT"); GameTooltip:SetText("CapyMorph")
  GameTooltip:AddLine("Left-click: open    Drag: move", 1, 1, 1); GameTooltip:Show()
end)
mmb:SetScript("OnLeave", function() GameTooltip:Hide() end)
mmPos((TMC.db() and TMC.db().minimapAngle) or 200)
