-- Independent prefix filtering over local phrase tails; never synthesize words.
local Query = require("bihua_phrase_query")
local M = {}

function M.query(input, strokes, data, budget, aliases)
  budget = math.max(0, math.min(120, budget or 120))
  local parts, reason = Query.parse(input)
  if not parts or #parts < 2 then return {}, {status=reason or "not_phrase", lookups=0, scanned=0} end
  local wildcard = input:find("?", 1, true) ~= nil
  local heads, seen, lookups = {}, {}, 0
  for _, variant in ipairs(Query.variants(parts[1], false, wildcard)) do
    if lookups >= budget then return {}, {status="query_too_wide", lookups=lookups, scanned=0, matches=0} end
    lookups = lookups + 1
    for _,text in ipairs(aliases and aliases.prefixes[variant.code] or {}) do
      if not seen[text] and data.codes[text] then
        seen[text]=true;heads[#heads+1]={text=text,
          score=require('bihua_personal_stroke_runtime').weight(strokes,text,#variant.code)}
      end
    end
    for _, row in ipairs(strokes.prefixes[variant.code] or {}) do
      if not seen[row[1]] and data.codes[row[1]] then
        seen[row[1]] = true
        heads[#heads + 1] = {text=row[1], score=row[2]}
      end
    end
  end
  table.sort(heads, function(a, b)
    return a.score ~= b.score and a.score > b.score or (a.score == b.score and a.text < b.text)
  end)
  local patterns = {}
  for position = 2, #parts do
    patterns[#patterns + 1] = (parts[position]:gsub("%?", "[hspnz]")) .. "[hspnz]*"
  end
  local pattern = "^" .. table.concat(patterns, "|") .. "$"
  local results, scanned, truncated = {}, 0, false
  for rank, first in ipairs(heads) do
    if lookups >= budget then truncated = true; break end
    lookups = lookups + 1
    local group = (data.tails[first.text] or {})[#parts - 1] or {}
    for _, tail in ipairs(group) do
      if scanned >= 20000 then truncated = true; break end
      scanned = scanned + 1
      local matches=tail[3]:match(pattern)~=nil
      if not matches and aliases then
        local chars,codes={},{}
        for _,cp in utf8.codes(tail[1]) do chars[#chars+1]=utf8.char(cp) end
        for code in tail[3]:gmatch('[^|]+') do codes[#codes+1]=code end
        matches=#chars==#parts-1 and #codes==#chars
        for i,char in ipairs(chars) do
          if not require('bihua_personal_stroke_runtime').matches(char,parts[i+1],codes[i],aliases.by_char) then matches=false;break end
        end
      end
      if matches then
        local function full(char,part,canonical)
          local alias=aliases and aliases.by_char[char]
          return #canonical==#part or alias and #alias==#part or false
        end
        local exact = full(first.text,parts[1],data.codes[first.text])
        local position = 2
        local chars={};for _,cp in utf8.codes(tail[1]) do chars[#chars+1]=utf8.char(cp) end
        for code in tail[3]:gmatch("[^|]+") do
          exact = exact and full(chars[position-1],parts[position],code)
          position = position + 1
        end
        results[#results + 1] = {text=first.text .. tail[1], packed=data.codes[first.text] .. "|" .. tail[3],
                                tier=wildcard and 2 or (exact and 0 or 1), source="static",
                                -- An explicit research baseline; not a claim of
                                -- reproducing the complete mobile final ranker.
                                score=2 * math.log(tail[2] + 1, 10) + 0.5 * first.score}
      end
    end
    if truncated then break end
  end
  table.sort(results, function(a, b)
    if a.tier ~= b.tier then return a.tier < b.tier end
    if a.score ~= b.score then return a.score > b.score end
    return a.text < b.text
  end)
  local out = {}
  for rank, row in ipairs(results) do
    if rank > 120 then break end
    row.codes = {}
    for code in row.packed:gmatch("[^|]+") do row.codes[#row.codes + 1] = code end
    out[#out + 1] = row
  end
  return out, {status=truncated and "query_too_wide" or "ok", lookups=lookups, scanned=scanned, matches=#results}
end
return M
