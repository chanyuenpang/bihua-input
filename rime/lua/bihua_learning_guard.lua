-- Observe explicit candidate selection; punctuation/ASCII commits do not learn.
local M = {}
local function remove_display(ctx)
  if not ctx.composition:empty() and ctx.composition:back():has_tag("bihua_no_candidate") then
    ctx.composition:toSegmentation():reset_length(0)
    return true
  end
  return false
end

function M.init(env)
  env.preedit_update = env.engine.context.update_notifier:connect(function(ctx)
    if env.preedit_updating then return end
    local stale = false
    for _, segment in ipairs(ctx.composition:toSegmentation():get_segments()) do
      if segment:has_tag("bihua_no_candidate") then stale = true; break end
    end
    if stale then
      env.preedit_updating = true
      ctx.composition:toSegmentation():reset_length(0)
      env.engine:compose(ctx)
      env.preedit_updating = false
    end
    if ctx:get_option("ascii_mode") or ctx.input == "" or ctx:has_menu() or
       not ctx.input:match("^[hspnz|?]+$") then return end
    local length = #ctx.input
    ctx.composition:toSegmentation():reset_length(0)
    local hidden = Segment(0, length)
    hidden.tags = Set({"phony", "bihua_no_candidate"})
    ctx.composition:push_back(hidden)
    local display = Segment(length, length)
    display.tags = Set({"phony", "placeholder", "bihua_no_candidate"})
    display.prompt = require("bihua_matcher").preedit(ctx.input)
    ctx.composition:push_back(display)
  end)
end

function M.fini(env)
  if env.preedit_update then env.preedit_update:disconnect() end
end

function M.func(key, env)
  local code = key.keycode
  local ctx = env.engine.context
  -- key_binder rewrites Enter to Space. Retain the original confirmation intent
  -- across that rewrite until commit_notifier consumes it.
  if not key:release() and not key:ctrl() and not key:alt() and not key:shift() and
     not ctx:get_option("ascii_mode") and ctx:has_menu() and
     (code == 0xff0d or code == 0xff8d) then
    ctx:set_property("bihua_close_after_commit", "1")
  end
  if not ctx:get_option("ascii_mode") and ctx.input ~= "" and not ctx:has_menu() and
     (code == 0x20 or code == 0xff0d or code == 0xff8d or code == 0xffb0) then
    return 1 -- No candidate exists: never commit a literal stroke code.
  end
  -- Unknown letters must never reach ascii_composer/express_editor, which may
  -- otherwise commit the first candidate and then insert the literal letter.
  if not ctx:get_option("ascii_mode") and not key:ctrl() and not key:alt() and not key:release() and
     ((code >= 0x41 and code <= 0x5a) or (code >= 0x61 and code <= 0x7a)) then
    local letter = string.char(code)
    local allowed = letter:match("^[hspdnz]$") or
                    ((letter == 'f' or letter == 't') and env.engine.schema.config:get_bool("bihua_matcher/phrase_enabled"))
    if not allowed then return 1 end
  end
  if ctx:get_property("bihua_feedback_session")~="" then
    require("bihua_association_runtime").before_key(key,ctx)
  end
  -- A physical question-mark key is punctuation. Only query_keys may insert
  -- the internal '?' operator (from T / keypad 6).
  if code == 0x3f and not key:release() and not key:ctrl() and not key:alt() and
     not ctx:get_option("ascii_mode") then
    ctx:set_property("bihua_explicit_selection", "0")
    ctx:set_property("bihua_selection_input", "")
    if not ctx.composition:empty() and ctx.composition:back():has_tag("prediction") then
      ctx:clear()
    elseif ctx:has_menu() then
      ctx:set_property("bihua_close_after_commit", "1")
      ctx:commit()
      ctx:clear()
    end
    env.engine:commit_text("？")
    return 1
  end
  if (key:ctrl() or key:alt()) and not ctx.composition:empty() and
     ctx.composition:back():has_tag("prediction") then
    return 0 -- Pass application shortcuts through without key_binder rewriting them into rejection events.
  end
  if not ctx.composition:empty() and ctx.composition:back():has_tag("bihua_no_candidate") and not key:release() then
    if code == 0xff1b then ctx:clear(); return 1 end
    if code >= 0x30 and code <= 0x39 then return 1 end
    if code == 0xff08 then remove_display(ctx); ctx:pop_input(1); return 1 end
    local stroke = ({[0xffb1]='h', [0xffb2]='s', [0xffb3]='p', [0xffb4]='n', [0xffb5]='z'})[code]
    if not stroke and code >= 0x61 and code <= 0x7a and not key:ctrl() and not key:alt() then
      local letter = string.char(code)
      if letter:match("^[hspdnz]$") then stroke = letter == 'd' and 'n' or letter end
    end
    if stroke then remove_display(ctx); ctx:push_input(stroke); return 1 end
  end
  if not key:release() and not key:ctrl() and not key:alt() and
     not ctx.composition:empty() and ctx.composition:back():has_tag("prediction") then
    local stroke = code == string.byte('h') or code == string.byte('s') or
                   code == string.byte('p') or code == string.byte('d') or
                   code == string.byte('n') or code == string.byte('z') or
                   (code >= 0xffb1 and code <= 0xffb5)
    if code == 0xff1b or code == 0xff08 then
      ctx:set_property("bihua_association_boundary", "cancel")
      ctx:clear()
      return 1 -- kAccepted: dismiss prediction without selecting a character.
    elseif stroke then
      ctx:clear() -- Ignore suggestions and start a normal stroke composition.
    end
  end
  local selected = env.engine.context:has_menu() and
    (code == 0x20 or code == 0xff0d or (code >= 0x31 and code <= 0x39)) and
    not key:ctrl() and not key:alt() and not key:shift() and not key:release()
  env.engine.context:set_property("bihua_explicit_selection", selected and "1" or "0")
  env.engine.context:set_property("bihua_selection_input", selected and env.engine.context.input or "")
  return 2 -- kNoop: selector/editor retain responsibility for processing the key.
end
return M
