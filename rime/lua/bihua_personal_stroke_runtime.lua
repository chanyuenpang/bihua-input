-- One small version header per query; full validation only for a new revision.
local M = {}
local snapshots = {}
local weight_cache = setmetatable({}, {__mode='k'})
local function han(cp)
  return cp >= 0x3400 and cp <= 0x9fff or cp >= 0xf900 and cp <= 0xfaff or cp >= 0x20000 and cp <= 0x323af
end
local function empty() return {revision=0, by_char={}, prefixes={}} end
local function report(env, status)
  env.engine.context:set_property('bihua_personal_stroke_load_status', status)
end
function M.refresh(env)
  local path = rime_api.get_user_data_dir() .. '/bihua_personal_strokes.tsv'
  local state = snapshots[path] or {good=empty()}; snapshots[path]=state
  local file, _, err = io.open(path, 'rb')
  if not file then
    report(env, err == 2 and state.good.revision == 0 and 'ok' or 'read_failed')
    env.personal_strokes=state.good; return state.good
  end
  local header = (file:read('*l') or ''):gsub('\r$', '')
  local revision = tonumber(header:match('^# bihua%-personal%-strokes%-v1\t(%d+)$'))
  if not revision or revision < 1 or revision > 9007199254740991 then
    file:close();report(env,'invalid_header');env.personal_strokes=state.good;return state.good
  end
  if revision < state.good.revision then
    file:close();report(env,'stale_revision');env.personal_strokes=state.good;return state.good
  end
  if revision == state.good.revision or revision == state.rejected then
    file:close();report(env,revision==state.rejected and 'invalid_batch' or 'ok')
    env.personal_strokes=state.good;return state.good
  end
  local ok, next_state = pcall(function()
    local result, count, bytes = {revision=revision, by_char={}, prefixes={}}, 0, #header
    for line in file:lines() do
      bytes=bytes+#line+1;assert(bytes<=4194304,'file too large')
      line=line:gsub('\r$', '')
      if line~='' then
        local char, code=line:match('^([^\t]+)\t([hspnz]+)$')
        assert(char and utf8.len(char)==1 and han(utf8.codepoint(char)) and #code<=52 and not result.by_char[char], 'invalid row')
        count=count+1;assert(count<=20000,'too many rows');result.by_char[char]=code
        for length=1,#code do
          local key=code:sub(1,length);local bucket=result.prefixes[key] or {}
          bucket[#bucket+1]=char;result.prefixes[key]=bucket
        end
      end
    end
    for _,bucket in pairs(result.prefixes) do table.sort(bucket) end
    -- Construct dependent phrase indexes before publishing this snapshot.
    if env.phrase_rows then result.phrase_index=require('bihua_phrase_query').new(env.phrase_rows,result.by_char) end
    return result
  end)
  file:close()
  if ok then state.good=next_state;state.rejected=nil
  else state.rejected=revision;log.error('bihua personal stroke batch rejected: '..tostring(next_state)) end
  env.personal_strokes=state.good
  report(env,ok and 'ok' or 'invalid_batch')
  return state.good
end
function M.matches(char, pattern, canonical, aliases)
  local lua_pattern='^'..pattern:gsub('%?', '[hspnz]')
  return canonical and canonical:match(lua_pattern)~=nil or aliases and aliases[char] and aliases[char]:match(lua_pattern)~=nil or false
end
-- An alias changes spelling only. Use the original character's score at the
-- same prefix length; truncated indexes fall back to its full/longer code.
function M.weight(data, char, length)
  local cache=weight_cache[data] or {};weight_cache[data]=cache
  local key=char..':'..length
  if cache[key]~=nil then return cache[key] end
  local code=data.codes[char]
  if not code then cache[key]=0;return 0 end
  local function find(size)
    for _,row in ipairs(data.prefixes[code:sub(1,size)] or {}) do
      if row[1]==char then return row[2] end
    end
  end
  local score=find(math.min(length,#code))
  if score==nil then
    for size=#code,1,-1 do score=find(size);if score~=nil then break end end
  end
  cache[key]=score or 0;return cache[key]
end
return M
