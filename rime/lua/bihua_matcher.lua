-- Standard stroke-prefix candidates.
-- Generated data is local research; the module contains no commercial data.
local M = {}
local stroke_symbols = {h="一", s="丨", p="丿", n="丶", d="丶", z="𠃌", ["|"]="‘", ["?"]="？"}
function M.preedit(input)
  return (input:gsub(".", function(char) return stroke_symbols[char] or char end))
end

function M.init(env)
  env.data = require("bihua_local_data")
  env.personal_runtime = require("bihua_personal_stroke_runtime")
  env.format_preedit = M.preedit
  local config = env.engine.schema.config
  require('bihua_character_learning').init(env)
  if config:get_bool("bihua_matcher/phrase_enabled") then
    env.phrase_runtime = require("bihua_phrase_runtime")
    env.phrase_runtime.init(env)
  end
  if config:get_bool("bihua_matcher/personal_association") then
    env.association_runtime = require("bihua_association_runtime")
    env.association_runtime.init(env)
  end
  if env.association_runtime or env.phrase_runtime then
    env.reset_selection = env.engine.context.commit_notifier:connect(function(context)
      context:set_property("bihua_explicit_selection", "0")
      context:set_property("bihua_selection_input", "")
    end)
  end
end

function M.fini(env)
  require('bihua_character_learning').fini(env)
  if env.phrase_runtime then env.phrase_runtime.fini(env) end
  if env.association_runtime then env.association_runtime.fini(env) end
  if env.reset_selection then env.reset_selection:disconnect(); env.reset_selection = nil end

end

function M.func(input, segment, env)
  local aliases = env.personal_runtime.refresh(env)
  if env.association_runtime and env.association_runtime.translate(segment, env) then return end
  if env.phrase_runtime and env.phrase_runtime.translate(input, segment, env) then return end
  if not input:match("^[hspnz]+$") then return end
  local direct = env.data.prefixes[input] or {}
  local seen, rows = {}, {}
  for index, row in ipairs(direct) do
    if not seen[row[1]] then
      seen[row[1]]=true;rows[#rows+1]={text=row[1],score=row[2],order=index}
    end
  end
  for index, text in ipairs(aliases.prefixes[input] or {}) do
    if not seen[text] then
      seen[text]=true;rows[#rows+1]={text=text,score=env.personal_runtime.weight(env.data,text,#input),
                                  order=#direct+index,personal=true}
    end
  end
  table.sort(rows,function(a,b) return a.score~=b.score and a.score>b.score or
                                          a.score==b.score and a.order<b.order end)
  require('bihua_character_learning').rank(rows,env)
  for rank,row in ipairs(rows) do
    if rank>120 then break end
    local candidate = Candidate(row.personal and 'bihua_personal_stroke' or 'bihua_direct',segment.start,segment._end,row.text,'')
    candidate.quality = 1000 - rank
    candidate.preedit = M.preedit(input)
    yield(candidate)
  end
end
return M
