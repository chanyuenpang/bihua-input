-- Explicit single-character choices, stored under the system's canonical code.
-- The immutable phone ranking remains the baseline for users without history.
local M = {}
local stores = {}
function M.init(env)
  if not env.engine.schema.config:get_bool('bihua_matcher/character_learning') then return end
  env.character_memory=Memory(env.engine,env.engine.schema,'bihua_character')
  local path=rime_api.get_user_data_dir()
  local state=stores[path]
  if not state then
    state={counts={}};stores[path]=state
    if env.character_memory:user_lookup('',true) then
      for entry in env.character_memory:iter_user() do
        local code=env.data.codes[entry.text]
        if code and entry.custom_code==code..' ' and entry.commit_count>0 then
          state.counts[entry.text]=entry.commit_count
        end
      end
    end
  end
  env.character_usage=state.counts
  env.character_commit=env.engine.context.commit_notifier:connect(function(ctx)
    local selected=ctx:get_selected_candidate()
    local candidate=selected and selected:get_genuine()
    if not candidate or ctx:get_property('bihua_explicit_selection')~='1' or
       ctx:get_property('bihua_selection_input')~=ctx.input then return end
    if candidate.type~='bihua_direct' and candidate.type~='bihua_wildcard' and
       candidate.type~='bihua_personal_stroke' then return end
    local text=candidate.text
    local code=env.data.codes[text]
    if not code or utf8.len(text)~=1 then return end
    local entry=DictEntry();entry.text=text;entry.custom_code=code..' '
    local saved=env.character_memory:update_userdict(entry,1,'')
    env.character_memory:finish_session()
    if saved then state.counts[text]=(state.counts[text] or 0)+1 end
    ctx:set_property('bihua_character_storage_status',saved and 'ok' or 'write_failed')
    ctx:set_property('bihua_character_usage',tostring(state.counts[text] or 0))
  end)
end
function M.rank(rows,env)
  if not env.character_usage then return end
  -- Three baseline positions per real choice, bounded to avoid destroying the
  -- useful phone frequency prior. This is independent of the query spelling.
  for index,row in ipairs(rows) do
    row.base_rank=index
    row.uses=env.character_usage[row.text] or 0
    row.learned_rank=math.max(1,index-math.min(60,row.uses*3))
  end
  table.sort(rows,function(a,b)
    if a.learned_rank~=b.learned_rank then return a.learned_rank<b.learned_rank end
    if a.uses~=b.uses then return a.uses>b.uses end
    return a.base_rank<b.base_rank
  end)
end
function M.fini(env)
  if env.character_commit then env.character_commit:disconnect() end
  if env.character_memory then env.character_memory:finish_session();env.character_memory:disconnect() end
end
return M
