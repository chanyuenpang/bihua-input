-- Small keypad operators are consumed before selector/key_binder.
local Query = require("bihua_phrase_query")
local M = {}
local defaults = {letter={h='h',s='s',p='p',n='d',z='z',wildcard='t',separator='f'},
                  keypad={h='KP_1',s='KP_2',p='KP_3',n='KP_4',z='KP_5',wildcard='KP_6',separator='KP_7'}}
local targets = {h='h',s='s',p='p',n='n',z='z',wildcard='KP_6',separator='KP_7'}
function M.init(env)
  env.bindings = {}
  local config=env.engine.schema.config
  for device,rows in pairs(defaults) do
    for action,fallback in pairs(rows) do
      local name=config:get_string('bihua_keys/'..device..'/'..action) or fallback
      env.bindings[KeyEvent(name).keycode]=targets[action]
    end
  end
  if (config:get_string('bihua_keys/letter_style') or 'standard')=='standard' then
    env.bindings[string.byte('n')]='n'
  end
  -- Number the remaining physical digits in keypad order. Configured strokes
  -- and operators always win; dot-held selection still uses printed numbers.
  env.free_digits={}
  local index=0
  for code=0xffb1,0xffb9 do
    if not env.bindings[code] then index=index+1;env.free_digits[code]=index end
  end
end
function M.func(key, env)
  if env.forwarding then return 2 end
  local ctx=env.engine.context
  if ctx:get_property('bihua_keymap_reset')~='' then
    env.select_held=false
    ctx:set_property('bihua_keymap_reset','')
  end
  if ctx:get_property('bihua_feedback_neutral_boundary')~='' or ctx:get_option('ascii_mode') then
    env.select_held=false
    if ctx:get_property('bihua_feedback_session')~='' then
      require('bihua_association_runtime').before_key(key,ctx)
    end
  end
  local code=key.keycode
  if ctx:get_option('ascii_mode') then return 2 end
  if code==0xffae and not key:ctrl() and not key:alt() then
    env.select_held=not key:release()
    return 1
  end
  if key:ctrl() or key:alt() or key:shift() then
    if env.free_digits[code] or env.select_held and code>=0xffb1 and code<=0xffb9 then return 0 end
    return 2
  end
  if key:release() then return 2 end
  local send
  local selection=env.select_held and code>=0xffb1 and code<=0xffb9 and code-0xffb0 or env.free_digits[code]
  if selection then
    if not ctx:has_menu() then return 1 end
    local segment=ctx.composition:back()
    local size=env.engine.schema.config:get_int('menu/page_size') or 9
    local page=math.floor(segment.selected_index/size)
    if selection>size or not segment.menu:get_candidate_at(page*size+selection-1) then return 1 end
    send=tostring(selection)
  elseif code==0xffab or code==0xffad then
    if not ctx:has_menu() then return 2 end
    if env.engine.schema.config:get_bool('bihua_keys/page_keypad')==false then return 2 end
    send=code==0xffab and 'Page_Down' or 'Page_Up'
  elseif code==0xffb0 then
    if not ctx:has_menu() then return 1 end
    send='space'
  else send=env.bindings[code] end
  if send then
    -- Inject canonical keys through the existing learning/selection pipeline.
    -- Recursive calls skip physical mapping, so custom letters cannot remap twice.
    env.forwarding=true
    local ok,err=pcall(function() env.engine:process_key(KeyEvent(send)) end)
    env.forwarding=false
    if not ok then error(err) end
    return 1
  end
  if code>=0x61 and code<=0x7a then return 1 end
  if code>=0xffb1 and code<=0xffb9 then return 1 end
  return 2
end

-- Canonical query operators run after physical-key normalization.
local physical_func=M.func
function M.func(key,env)
  if key.keycode==0xffd5 and not key:release() then -- F24, internal mouse intent only
    local ctx=env.engine.context
    local action=ctx:get_property('bihua_mouse_action')
    ctx:set_property('bihua_mouse_action','')
    if action=='expose' then
      local first=ctx:get_property('bihua_mouse_expose_first')
      local count=ctx:get_property('bihua_mouse_expose_count')
      ctx:set_property('bihua_mouse_expose_first','')
      ctx:set_property('bihua_mouse_expose_count','')
      require('bihua_association_runtime').expose(ctx,first,count)
      return 1
    end
    local canonical={h='h',s='s',p='p',n='n',z='z',wildcard='KP_6'}
    if canonical[action] and not ctx:get_option('ascii_mode') then
      env.forwarding=true
      local ok,err=pcall(function() env.engine:process_key(KeyEvent(canonical[action])) end)
      env.forwarding=false
      if not ok then error(err) end
    end
    return 1
  end
  if not env.forwarding then return physical_func(key,env) end
  if key:release() or key:ctrl() or key:alt() or key:shift() then return 2 end
  local code, ctx = key.keycode, env.engine.context
  local separator = code == 0xffb7 or code == string.byte('f')
  local wildcard = code == 0xffb6 or code == string.byte('t')
  if not separator and not wildcard then return 2 end
  if ctx:get_option("ascii_mode") then return 2 end
  if not ctx.composition:empty() and ctx.composition:back():has_tag("prediction") then
    return 1 -- An operator never chooses a prediction or starts an empty query.
  end
  local current = ctx.input
  if current == "" then return 1 end
  local proposed = current .. (separator and "|" or "?")
  local parsed, reason = Query.parse(proposed, separator)
  if parsed and not (separator and (#parsed >= 4 or current:sub(-1) == "|")) then
    if not ctx.composition:empty() and ctx.composition:back():has_tag("bihua_no_candidate") then
      ctx.composition:toSegmentation():reset_length(0)
    end
    ctx.input = proposed
    ctx:set_property("bihua_query_status", "ok")
  else ctx:set_property("bihua_query_status", reason or "query_too_wide") end
  return 1
end
return M
