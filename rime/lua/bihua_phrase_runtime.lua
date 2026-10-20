local Query = require("bihua_phrase_query")
local M = {}
local last_good = {}
function M.init(env)
  local rows, seen, rejected = {}, {}, 0
  local path = rime_api.get_user_data_dir() .. "/bihua_personal_phrases.tsv"
  local file, open_error, open_code = io.open(path, "rb")
  local read_failed = not file and open_code ~= 2
  if read_failed then rejected = 1 end
  if file then
    for line in file:lines() do
      line = line:gsub("\r$", "")
      if line:sub(1, 1) ~= "#" and line ~= "" then
        local text, packed, weight = line:match("^([^\t]+)\t([^\t]+)\t([^\t]+)$")
        local codes = {}
        for code in (packed or ""):gmatch("[^|]+") do codes[#codes + 1] = code end
        if text and not seen[text] and utf8.len(text) == #codes and #codes >= 2 and #codes <= 4 and table.concat(codes, "|") == packed then
          local valid = true
          for _, code in ipairs(codes) do if not code:match("^[hspnz]+$") or #code > 52 then valid = false end end
          if valid and tonumber(weight) and tonumber(weight) >= 0 and tonumber(weight) <= 1000000000 then
            rows[#rows + 1] = {text=text, codes=codes, weight=tonumber(weight)}
            seen[text] = true
          else rejected = rejected + 1 end
        else rejected = rejected + 1 end
        if #rows > 20000 then rejected = rejected + 1; break end
      end
    end
    file:close()
  end
  if rejected > 0 then rows = last_good[path] or {}; log.error("bihua personal phrase batch rejected")
  else last_good[path] = rows end
  env.engine.context:set_property("bihua_phrase_load_status", read_failed and "read_failed" or (rejected > 0 and "invalid_batch" or "ok"))
  env.engine.context:set_property("bihua_phrase_rejected_rows", tostring(rejected))
  env.phrase_index = Query.new(rows)
  env.phrase_rows=rows
  env.phrase_alias_revision=-1
  if env.engine.schema.config:get_bool("bihua_matcher/mobile_phrases") then
    local ok, data = pcall(require, "bihua_local_phrase_data")
    if ok then env.phone_phrase_data = data
    else log.error("bihua local phrase profile unavailable") end
  end
  env.phrase_memory = Memory(env.engine, env.engine.schema, "bihua_phrase")
  env.phrase_offered = {}
  env.phrase_commit = env.engine.context.commit_notifier:connect(function(ctx)
    local candidate = ctx:get_selected_candidate()
    local genuine = candidate and candidate:get_genuine()
    local row = genuine and genuine.type == "bihua_phrase" and env.phrase_offered[genuine.text]
    if row and ctx:get_property("bihua_explicit_selection") == "1" and
       ctx:get_property("bihua_selection_input") == ctx.input then
      local entry = DictEntry()
      entry.text, entry.custom_code = row.text, table.concat(row.codes, "|") .. " "
      local saved = env.phrase_memory:update_userdict(entry, 1, "")
      env.phrase_memory:finish_session()
      ctx:set_property("bihua_phrase_storage_status", saved and "ok" or "write_failed")
    end
  end)
end

function M.translate(input, segment, env)
  if not input:find("[?|]") then return false end
  local personal=env.personal_strokes or {revision=0,by_char={},prefixes={}}
  if env.phrase_alias_revision~=personal.revision then
    env.phrase_index=Query.new(env.phrase_rows,personal.by_char)
    env.phrase_alias_revision=personal.revision
  end
  if input:find("|", 1, true) then
    local rows, diagnostics = env.phrase_index:query(input, env.fuzzy_enabled)
    if env.phone_phrase_data then
      local phone, phone_diagnostics = require("bihua_phone_phrases").query(input, env.data, env.phone_phrase_data, 120 - diagnostics.lookups, personal)
      local seen = {}
      for _, row in ipairs(rows) do row.source = "personal"; seen[row.text] = true end
      for _, row in ipairs(phone) do
        if not seen[row.text] then rows[#rows + 1] = row; seen[row.text] = true end
      end
      diagnostics.lookups = diagnostics.lookups + phone_diagnostics.lookups
      if phone_diagnostics.status ~= "ok" then diagnostics.status = phone_diagnostics.status end
      env.engine.context:set_property("bihua_phone_phrase_scanned", tostring(phone_diagnostics.scanned))
      env.engine.context:set_property("bihua_phone_phrase_matches", tostring(phone_diagnostics.matches or 0))
    end
    local function compare(a, b)
      if a.tier ~= b.tier then return a.tier < b.tier end
      if a.source ~= b.source then return a.source == "personal" end
      if a.score ~= b.score then return a.score > b.score end
      return a.text < b.text
    end
    table.sort(rows, compare)
    while #rows > 120 do table.remove(rows) end
    local usage = {}
    for _, row in ipairs(rows) do
      local key = table.concat(row.codes, "|") .. " "
      if env.phrase_memory:user_lookup(key:sub(1, -2), false) then
        for entry in env.phrase_memory:iter_user() do
          if entry.text == row.text and entry.custom_code == key then usage[row.text] = entry.commit_count end
        end
      end
      row.score = row.score + math.min(3, (usage[row.text] or 0) * 0.4)
    end
    table.sort(rows, compare)
    env.engine.context:set_property("bihua_query_status", diagnostics.status)
    env.engine.context:set_property("bihua_query_lookups", tostring(diagnostics.lookups))
    env.phrase_offered = {}
    for rank, row in ipairs(rows) do
      env.phrase_offered[row.text] = row
      env.engine.context:set_property("bihua_phrase_usage_" .. row.text, tostring(usage[row.text] or 0))
      local candidate = Candidate("bihua_phrase", segment.start, segment._end, row.text, "")
      candidate.quality = 1000 - rank
      candidate.preedit = env.format_preedit(input)
      yield(candidate)
    end
  else
    local parts = Query.parse(input)
    if not parts then return true end
    local rows, seen = {}, {}
    for _, variant in ipairs(Query.variants(input, false, true)) do
      for rank, row in ipairs(env.data.prefixes[variant.code] or {}) do
        if rank > 20 then break end
        if not seen[row[1]] then
          seen[row[1]] = true
          rows[#rows + 1] = {text=row[1], score=row[2]}
        end
      end
      for _,text in ipairs(personal.prefixes[variant.code] or {}) do
        if not seen[text] then
          seen[text]=true;rows[#rows+1]={text=text,
            score=require('bihua_personal_stroke_runtime').weight(env.data,text,#variant.code),personal=true}
        end
      end
    end
    table.sort(rows, function(a, b) return a.score ~= b.score and a.score > b.score or
                                              (a.score == b.score and a.text < b.text) end)
    require('bihua_character_learning').rank(rows,env)
    for rank, row in ipairs(rows) do
      if rank>120 then break end
      local candidate = Candidate(row.personal and "bihua_personal_stroke" or "bihua_wildcard", segment.start, segment._end, row.text, "")
      candidate.quality = 1000 - rank
      candidate.preedit = env.format_preedit(input)
      yield(candidate)
    end
  end
  return true
end

function M.fini(env)
  if env.phrase_commit then env.phrase_commit:disconnect() end
  if env.phrase_memory then env.phrase_memory:finish_session(); env.phrase_memory:disconnect() end
end
return M
