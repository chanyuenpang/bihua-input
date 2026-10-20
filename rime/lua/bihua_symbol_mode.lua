-- Session-local punctuation menu. It suspends rather than commits a query.
local M = {}
local sessions,serial={},0
local function owner(ctx) return sessions[ctx:get_property('bihua_symbol_session')] end
function M.active(ctx) local env=owner(ctx);return env and env.symbol_phase=='active' end
local function transition(env,fn)
  local ctx=env.engine.context
  ctx:set_property('bihua_symbol_transition','1')
  local ok,err=pcall(fn)
  ctx:set_property('bihua_symbol_transition','')
  if not ok then error(err) end
end
local function restore(env)
  local ctx=env.engine.context
  local suspended=env.symbol_suspended
  env.symbol_phase='inactive';env.symbol_suspended=nil
  transition(env,function()
    ctx:set_property('bihua_symbol_active','')
    ctx:clear()
    if not suspended then return end
    if suspended.input~='' then ctx.input=suspended.input
    elseif suspended.prediction then
      local segment=Segment(0,0);segment.tags=Set({'prediction','placeholder'})
      ctx.composition:push_back(segment);env.engine:compose(ctx)
    end
    if suspended.index and not ctx.composition:empty() then
      local segment=ctx.composition:back()
      if segment.menu and segment.menu:get_candidate_at(suspended.index) then segment.selected_index=suspended.index end
    end
  end)
end
function M.cancel(ctx)
  local env=owner(ctx)
  if env and env.symbol_phase=='active' then restore(env);return true end
  return false
end
function M.toggle(ctx)
  local env=owner(ctx)
  if not env or ctx:get_option('ascii_mode') then return false end
  if env.symbol_phase=='active' then restore(env);return true end
  if env.symbol_phase~='inactive' then return false end
  if #env.symbol_items==0 then ctx:set_property('bihua_symbol_status','configuration_missing');return false end
  local segment=not ctx.composition:empty() and ctx.composition:back()
  env.symbol_suspended={input=ctx.input,prediction=segment and segment:has_tag('prediction'),index=segment and segment.selected_index}
  env.symbol_phase='active'
  transition(env,function()
    ctx:set_property('bihua_symbol_active','1')
    ctx:clear()
    local menu=Segment(0,0);menu.tags=Set({'bihua_symbol','placeholder'});menu.prompt='常用符号'
    ctx.composition:push_back(menu);env.engine:compose(ctx)
  end)
  ctx:set_property('bihua_symbol_status','ok')
  return true
end
function M.init(env)
  serial=serial+1;env.symbol_session=tostring(serial);env.symbol_phase='inactive';env.symbol_items={}
  sessions[env.symbol_session]=env
  local ctx=env.engine.context;ctx:set_property('bihua_symbol_session',env.symbol_session)
  env.symbol_page_keys={}
  for index=0,255 do
    local path='key_binder/bindings/@'..index
    local accept=env.engine.schema.config:get_string(path..'/accept')
    if not accept then break end
    local send=env.engine.schema.config:get_string(path..'/send')
    if env.engine.schema.config:get_string(path..'/when')=='has_menu' and (send=='Page_Up' or send=='Page_Down') then
      env.symbol_page_keys[KeyEvent(accept):repr()]=send=='Page_Up' and -1 or 1
    end
  end
  for index=0,127 do
    local item=env.engine.schema.config:get_string('bihua_symbols/items/@'..index)
    if not item then break end
    assert(item~='' and not item:find('[%c]'),'invalid bihua_symbols item')
    env.symbol_items[#env.symbol_items+1]=item
  end
  env.symbol_commit=ctx.commit_notifier:connect(function(context)
    local selected=context:get_selected_candidate()
    local genuine=selected and selected:get_genuine()
    if env.symbol_phase=='active' and genuine and genuine.type=='bihua_symbol' then
      env.symbol_phase='commit-pending'
      -- A symbol boundary never creates a manual character or +/- feedback.
      context:set_property('bihua_symbol_neutral_commit','1')
    end
  end)
  env.symbol_update=ctx.update_notifier:connect(function(context)
    if context:get_property('bihua_symbol_transition')~='' then return end
    if env.symbol_phase=='commit-pending' and context.input=='' and context.composition:empty() then
      if env.symbol_suspended then env.symbol_suspended.prediction=false end
      restore(env)
      context:set_property('bihua_symbol_neutral_commit','')
    elseif env.symbol_phase=='active' and context:get_option('ascii_mode') then restore(env) end
  end)
  env.symbol_option=ctx.option_update_notifier:connect(function(context)
    if context:get_option('ascii_mode') then M.cancel(context) end
  end)
end
function M.fini(env)
  sessions[env.symbol_session]=nil
  if env.symbol_commit then env.symbol_commit:disconnect() end
  if env.symbol_update then env.symbol_update:disconnect() end
  if env.symbol_option then env.symbol_option:disconnect() end
end
function M.translate(segment,env)
  if not segment:has_tag('bihua_symbol') then return false end
  for index,text in ipairs(env.symbol_items) do
    local candidate=Candidate('bihua_symbol',segment.start,segment._end,text,'')
    candidate.quality=1000-index;yield(candidate)
  end
  return true
end
-- nil means leave the event to the ordinary physical/query key pipeline.
function M.key(key,ctx)
  local env=owner(ctx)
  if not env then return nil end
  if ctx:get_option('ascii_mode') then M.cancel(ctx);return nil end
  if key:ctrl() or key:alt() or key:super() then return env.symbol_phase=='active' and 0 or nil end
  if key.keycode==0xff7f and (env.engine.schema.config:get_string('bihua_keys/symbol_toggle') or 'Num_Lock')=='Num_Lock' then
    if not key:release() then M.toggle(ctx) end
    return 1
  end
  if env.symbol_phase~='active' then return nil end
  if key.keycode==0xffe1 or key.keycode==0xffe2 or key.keycode==0xffe5 then M.cancel(ctx);return nil end
  if key:release() then return 1 end
  local code=key.keycode
  if code==0xff1b or code==0xff08 then M.cancel(ctx);return 1 end
  if ctx.composition:empty() then return 1 end
  local segment=ctx.composition:back()
  local size=env.engine.schema.config:get_int('menu/page_size') or 9
  local index=segment.selected_index
  local digit=code>=0xffb1 and code<=0xffb9 and code-0xffb0 or code>=0x31 and code<=0x39 and code-0x30
  local choose=digit or code==0xffb0 or code==0x20 or code==0xff0d or code==0xff8d
  if choose then
    local target=digit and math.floor(index/size)*size+digit-1 or index
    if (not digit or digit<=size) and segment.menu:get_candidate_at(target) then
      segment.selected_index=target;ctx:commit()
    end
    return 1
  end
  local delta=({[0xffaf]=-1,[0xffaa]=1,[0xff51]=-1,[0xff53]=1,[0xff52]=-1,[0xff54]=1})[code]
  local paging=env.symbol_page_keys[key:repr()] or ({[0xffad]=-1,[0xffab]=1,[0xff55]=-1,[0xff56]=1})[code]
  local target=delta and index+delta or paging and (math.floor(index/size)+paging)*size
  if target and target>=0 and segment.menu:get_candidate_at(target) then segment.selected_index=target end
  return 1
end
return M
