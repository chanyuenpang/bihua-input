-- Rime adapter for the offline association core and stroke-filtered continuations.
local Core = require("bihua_association_core")
local Store = require("bihua_association_store")
local Episode = require("bihua_feedback_episode")
local M = {}
local sessions = {}
local function neutral_boundary(ctx,env)
  if ctx:get_property("bihua_feedback_neutral_boundary")=="" then return false end
  ctx:set_property("bihua_feedback_neutral_boundary","")
  if env.feedback_episode then env.feedback_episode:abandon() end
  env.association_carry=nil
  env.association_pending=false
  env.association=env.association_store.state
  if env.association_store.active_session==env.association_session then env.association:boundary() end
  return true
end

local function capture_range(ctx, env, first, count)
  local episode=env.feedback_episode
  if not episode or episode.closed or not ctx:has_menu() or ctx.composition:empty() then return end
  local segment=ctx.composition:back()
  local prediction=segment:has_tag("prediction")
  local carry=env.association_carry
  if not prediction and not (carry and carry.input==ctx.input) then return end
  if prediction then ctx:set_property("bihua_prediction_menu_active","1") end
  -- Read the filtered menu: simplified deduplication can change row indices.
  for index=first,first+count-1 do
    local candidate=segment.menu:get_candidate_at(index)
    if not candidate then break end
    local genuine=candidate:get_genuine()
    if carry and carry.input==ctx.input and carry.active[candidate.text] then
      episode:note(carry.active[candidate.text])
    elseif genuine and genuine.type=="bihua_association" then
      for _,row in ipairs(env.association_rows) do
        if row.suffix==genuine.text then episode:note(row);break end
      end
    end
  end
  ctx:set_property("bihua_feedback_visible_count",tostring(#episode.visible))
end
local function capture_page(ctx,env)
  -- Absolute mouse/navigation selection may target a row before it is painted.
  -- Its actual visible range was already registered by the native UI ack;
  -- selecting must not fabricate exposure of that target's whole Rime page.
  if ctx:get_property("bihua_mouse_absolute_selection")=="1" then return end
  if ctx.composition:empty() then return end
  local page=math.floor(ctx.composition:back().selected_index/env.page_size)
  capture_range(ctx,env,page*env.page_size,env.page_size)
  ctx:set_property("bihua_feedback_page",tostring(page))
end
function M.expose(ctx,first,count)
  local env=sessions[ctx:get_property("bihua_feedback_session")]
  if not env or ctx:get_option("ascii_mode") or
     ctx:get_property("bihua_feedback_neutral_boundary")~="" then return end
  first=tonumber(first);count=tonumber(count)
  if not first or not count or first<0 or count<1 or count>5*env.page_size or
     first%1~=0 or count%1~=0 then return end
  capture_range(ctx,env,first,count)
end
local function persist(ctx, env)
  local saved,reason=Store.save(env.association_store)
  env.association=env.association_store.state
  ctx:set_property("bihua_personal_storage_status",env.association_store.status)
  if not saved then log.error("bihua feedback save: "..tostring(reason)) end
  return saved
end
local function finish_ignore(ctx,env,save)
  local episode=env.feedback_episode
  local visible=episode and episode:close() or {}
  if env.association_store.active_session==env.association_session and env.association:ignore(visible) then
    if save~=false then persist(ctx,env) end
  end
end
local function first_prediction_page(ctx,env)
  local rows={}
  local segment=ctx.composition:back()
  for index=0,env.page_size-1 do
    local candidate=segment.menu:get_candidate_at(index)
    if not candidate then break end
    local genuine=candidate:get_genuine()
    if genuine and genuine.type=="bihua_association" then
      for _,row in ipairs(env.association_rows) do
        if row.suffix==genuine.text then
          rows[#rows+1]={row=row,text=candidate.text}
          break
        end
      end
    end
  end
  return rows
end

function M.before_key(key,ctx)
  if ctx:get_property('bihua_symbol_active')~='' or ctx:get_property('bihua_symbol_transition')~='' then return end
  local env=sessions[ctx:get_property("bihua_feedback_session")]
  if not env then return end
  env.association=env.association_store.state
  if ctx:get_option("ascii_mode") then
    if env.feedback_episode then env.feedback_episode:abandon() end
    env.association_carry=nil
    return
  end
  if neutral_boundary(ctx,env) then
    if not ctx.composition:empty() and ctx.composition:back():has_tag("prediction") then ctx:clear() end
    return
  end
  capture_page(ctx,env)
  local episode=env.feedback_episode
  if not episode or episode.closed or key:release() or key:ctrl() or key:alt() then return end
  local code=key.keycode
  local stroke=(code>=0xffb1 and code<=0xffb5) or
    (code>=0x61 and code<=0x7a and string.char(code):match("^[hspdnz]$"))
  if stroke and not ctx.composition:empty() and ctx.composition:back():has_tag("prediction") then
    -- Keep the original feedback episode open while the next character is
    -- narrowed by strokes. Merely matching never changes persistent weights.
    env.association_carry={rows=first_prediction_page(ctx,env),starting=true,active={}}
    return
  end
  if env.association_carry then
    if code==0xff1b or (code==0xff08 and ctx.input=="") then
      finish_ignore(ctx,env)
      env.association_carry=nil
    end
    return
  end
  if code==0xff1b or code==0xff08 or stroke then
    finish_ignore(ctx,env)
  end
end

function M.filter(input,ctx)
  if ctx:get_property('bihua_symbol_active')~='' or ctx:get_property('bihua_symbol_transition')~='' then
    for candidate in input:iter() do yield(candidate) end
    return
  end
  local env=sessions[ctx:get_property("bihua_feedback_session")]
  local carry=env and env.association_carry
  if not carry or not ctx.input:match("^[hspnz?]+$") then
    for candidate in input:iter() do yield(candidate) end
    return
  end
  local candidates,by_text={},{}
  for candidate in input:iter() do
    candidates[#candidates+1]=candidate
    by_text[candidate.text]=candidate
  end
  local function matching(item)
    if by_text[item.text] then return by_text[item.text] end
    -- Prefix tables are bounded. A continuation with a known standard code
    -- must not disappear merely because its normal rank is beyond that bound.
    local code=env.data.codes and env.data.codes[item.row.suffix]
    if code and code:match("^"..ctx.input:gsub("%?",".")) then
      local segment=ctx.composition:back()
      local candidate=Candidate("bihua_association_stroke",segment.start,segment._end,item.text,"")
      candidate.preedit=require("bihua_matcher").preedit(ctx.input)
      return candidate
    end
  end
  if not carry.pool then
    carry.pool={}
    for _,item in ipairs(carry.rows) do
      if #carry.pool<env.page_size-1 and matching(item) then
        carry.pool[#carry.pool+1]=item
      end
    end
    carry.prefix=ctx.input
  end
  carry.starting=false
  carry.input=ctx.input
  carry.active={}
  local promoted={}
  if ctx.input:sub(1,#carry.prefix)==carry.prefix then
    for _,item in ipairs(carry.pool) do
      local candidate=matching(item)
      if candidate then
        carry.active[candidate.text]=item.row
        promoted[#promoted+1]=candidate
      end
    end
  end
  ctx:set_property("bihua_carried_count",tostring(#promoted))
  for _,candidate in ipairs(promoted) do yield(candidate) end
  for _,candidate in ipairs(candidates) do
    if not carry.active[candidate.text] then yield(candidate) end
  end
end

function M.init(env)
  env.association_store = Store.open(rime_api.get_user_data_dir() .. "/bihua_personal_association_v1.jsonl")
  env.association = env.association_store.state
  local config = env.engine.schema.config
  env.prediction_limit = 9 * math.max(1, math.min(5, config:get_int("bihua_association/pages") or 5))
  env.page_size=math.max(1,math.min(9,config:get_int("menu/page_size") or 9))
  env.association_session = tostring(env)
  env.association_rows = {}
  env.association_depth = 0
  if env.engine.schema.config:get_bool("bihua_matcher/static_association") then
    local ok, data = pcall(require, "bihua_local_associations")
    if ok and type(data) == "table" then env.static_associations = data
    else log.error("bihua static association profile unavailable") end
  end
  env.association_cc = assert(Opencc("t2s.json"))
  local context = env.engine.context
  sessions[env.association_session]=env
  context:set_property("bihua_feedback_session",env.association_session)
  context:set_property("bihua_prediction_menu_active","")
  local loaded = 0
  for _,record in pairs(env.association.confirmed) do if record.positive_count>0 then loaded=loaded+1 end end
  context:set_property("bihua_loaded_relations", tostring(loaded))
  context:set_property("bihua_personal_storage_status", env.association_store.status)
  env.association_commit = context.commit_notifier:connect(function(ctx)
    if ctx:get_property('bihua_symbol_neutral_commit')=='1' then
      if env.feedback_episode then env.feedback_episode:abandon() end
      env.association=env.association_store.state
      env.association:boundary();env.association_depth=0
      env.association_pending=false;env.association_carry=nil
      ctx:set_property('bihua_carried_count','');persist(ctx,env)
      return
    end
    local close_after_commit = ctx:get_property("bihua_close_after_commit") == "1"
    ctx:set_property("bihua_close_after_commit", "")
    env.association = env.association_store.state
    if env.association_store.active_session ~= env.association_session then
      env.association:boundary()
      env.association_store.active_session = env.association_session
    end
    local selected = ctx:get_selected_candidate()
    local genuine = selected and selected:get_genuine()
    local explicit = ctx:get_property("bihua_explicit_selection") == "1"
    local text = ctx:get_commit_text()
    local carry=env.association_carry
    local carried=carry and carry.input==ctx.input and carry.active[text]
    if genuine and (genuine.type == "bihua_association" or carried) then
      local row=carried
      if not row then
        for _, offered in ipairs(env.association_rows) do
          if offered.suffix == text then row = offered; break end
        end
      end
      if row then
        capture_page(ctx,env)
        local visible=env.feedback_episode and env.feedback_episode:close() or {}
        local _, reason = env.association:select(row, explicit,visible)
        if reason == "stale_candidate" then
          env.association:boundary()
          env.association_depth = 0
        else env.association_depth = env.association_depth + 1 end
      else env.association:boundary() end
    elseif genuine and explicit and
           (genuine.type == "bihua_direct" or genuine.type == "bihua_personal_stroke" or genuine.type == "bihua_wildcard" or genuine.type == "bihua_fuzzy" or
            genuine.type == "bihua_fuzzy_learnable") then
      if carry then finish_ignore(ctx,env,false) end
      env.association:observe(env.association_cc:convert(text), "manual_stroke_char")
      env.association_depth = 0
    else
      if env.feedback_episode then env.feedback_episode:abandon() end
      env.association:boundary()
      env.association_depth = 0
    end
    env.association_carry=nil
    ctx:set_property("bihua_carried_count","")
    local saved, reason = Store.save(env.association_store)
    env.association = env.association_store.state
    ctx:set_property("bihua_personal_storage_status", env.association_store.status)
    if not saved then log.error("bihua personal association: " .. tostring(reason)) end
    if close_after_commit then
      if env.feedback_episode then env.feedback_episode:abandon() end
      env.association:boundary()
      env.association_depth = 0
      env.association_pending = false
    else
      env.association_pending = not env.association_store.read_only and env.association_depth < 7
    end
  end)
  env.association_update = context.update_notifier:connect(function(ctx)
    if ctx:get_property('bihua_symbol_active')~='' or ctx:get_property('bihua_symbol_transition')~='' then return end
    if env.association_updating then return end
    if ctx.composition:empty() or not ctx.composition:back():has_tag("prediction") then
      ctx:set_property("bihua_prediction_menu_active","")
    end
    env.association = env.association_store.state
    if neutral_boundary(ctx,env) then return end
    if env.association_store.active_session ~= env.association_session then
      if env.feedback_episode then env.feedback_episode:abandon() end
      env.association_pending = false
      return
    end
    capture_page(ctx,env)
    if env.association_carry and not env.association_carry.starting and ctx.input=="" and ctx.composition:empty() then
      finish_ignore(ctx,env)
      env.association_carry=nil
    end
    if env.feedback_episode and not env.feedback_episode.closed and
       not env.association_carry and
       (ctx.input~="" or ctx.composition:empty() or not ctx.composition:back():has_tag("prediction")) then
      env.feedback_episode:abandon()
    end
    if ctx:get_property("bihua_association_boundary") ~= "" then
      env.association = env.association_store.state
      env.association:boundary()
      env.association_pending = false
      ctx:set_property("bihua_association_boundary", "")
    end
    if not env.association_pending or ctx.input ~= "" or not ctx.composition:empty() then return end
    env.association_pending = false
    local previous = env.association.context[#env.association.context]
    env.association_rows = env.association:query(env.prediction_limit, env.static_associations and env.static_associations[previous])
    ctx:set_property("bihua_manual_history_size", tostring(#env.association.window))
    local count = 0
    for _,record in pairs(env.association.confirmed) do if record.positive_count>0 then count=count+1 end end
    ctx:set_property("bihua_confirmed_relations", tostring(count))
    if #env.association_rows == 0 then return end
    env.feedback_episode=Episode.new(env.association_rows,env.page_size)
    env.association_updating = true
    local segment = Segment(0, 0)
    segment.tags = Set({"prediction", "placeholder"})
    ctx.composition:push_back(segment)
    env.engine:compose(ctx)
    capture_page(ctx,env)
    env.association_updating = false
  end)
  env.feedback_page_select=context.select_notifier:connect(function(ctx) capture_page(ctx,env) end)
end

function M.translate(segment, env)
  if not segment:has_tag("prediction") then return false end
  for rank, row in ipairs(env.association_rows or {}) do
    local candidate = Candidate("bihua_association", segment.start, segment._end, row.suffix, "")
    candidate.quality = 1000 - rank
    yield(candidate)
  end
  return true
end

function M.fini(env)
  sessions[env.association_session]=nil
  if env.feedback_episode then env.feedback_episode:abandon() end
  if env.feedback_page_select then env.feedback_page_select:disconnect() end
  if env.association_commit then env.association_commit:disconnect() end
  if env.association_update then env.association_update:disconnect() end
end
return M
