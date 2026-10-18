-- Bounded personal phrase lookup. Query operators never become learned codes.
local M = {}
local Index = {}
Index.__index = Index

function M.parse(input, allow_trailing)
  if #input > 99 or input:find("[^hspnz?|]") then return nil, "invalid_query" end
  local parts, wildcards = {}, 0
  for part in (input .. "|"):gmatch("(.-)|") do
    if part == "" then
      if allow_trailing and #parts > 0 and input:sub(-1) == "|" then return parts, "incomplete" end
      return nil, "empty_segment"
    end
    if #part > 24 or not part:find("[hspnz]") then return nil, "invalid_segment" end
    local _, count = part:gsub("?", "")
    wildcards = wildcards + count
    if wildcards > 2 or #parts >= 4 then return nil, "query_too_wide" end
    parts[#parts + 1] = part
  end
  return parts
end

function M.new(rows, aliases)
  local self = setmetatable({rows={}, prefixes={}, aliases=aliases or {}, chars={}}, Index)
  assert(#rows <= 20000, "Personal vocabulary exceeds 20000 entries")
  local seen = {}
  for _, row in ipairs(rows) do
    assert(type(row.text) == "string" and utf8.len(row.text) == #row.codes and
           #row.codes >= 2 and #row.codes <= 4 and not seen[row.text], "Invalid or duplicate phrase")
    seen[row.text] = true
    self.rows[#self.rows + 1] = row
    local id = #self.rows
    local chars={};for _,cp in utf8.codes(row.text) do chars[#chars+1]=utf8.char(cp) end
    self.chars[id]=chars
    for position, code in ipairs(row.codes) do
      assert(code:match("^[hspnz]+$") and #code <= 52, "Invalid canonical phrase code")
      local seen_prefix={}
      for _,code in ipairs({code,self.aliases[chars[position]]}) do
      for length = 1, #code do
        local key = #row.codes .. ":" .. position .. ":" .. code:sub(1, length)
        if not seen_prefix[key] then
        seen_prefix[key]=true
        local bucket = self.prefixes[key] or {}
        bucket[#bucket + 1] = id
        self.prefixes[key] = bucket
        end
      end
      end
    end
  end
  for _, bucket in pairs(self.prefixes) do
    table.sort(bucket, function(a, b)
      local wa, wb = self.rows[a].weight or 1, self.rows[b].weight or 1
      return wa ~= wb and wa > wb or (wa == wb and self.rows[a].text < self.rows[b].text)
    end)
  end
  return self
end

local function variants(part, fuzzy, wildcards)
  local out = {{code=part, cost=0}}
  if wildcards then
    out = {}
    local function expand(prefix, offset)
      if offset > #part then out[#out + 1] = {code=prefix, cost=0}; return end
      local char = part:sub(offset, offset)
      if char == "?" then
        for stroke in ("hspnz"):gmatch(".") do expand(prefix .. stroke, offset + 1) end
      else expand(prefix .. char, offset + 1) end
    end
    expand("", 1)
  elseif fuzzy then
    for position = 1, #part - 1 do
      local a, b = part:sub(position, position), part:sub(position + 1, position + 1)
      if a ~= b then
        out[#out + 1] = {code=part:sub(1, position - 1) .. b .. a .. part:sub(position + 2), cost=1}
      end
    end
  end
  return out
end
M.variants = variants

function Index:query(input, fuzzy, usage)
  local parts, error = M.parse(input)
  if not parts or #parts < 2 then return {}, {status=error or "not_phrase", lookups=0} end
  local wildcard = input:find("?", 1, true) ~= nil
  local choices, smallest, lookups = {}, nil, 0
  for position, part in ipairs(parts) do
    choices[position] = variants(part, fuzzy, wildcard)
    local ids, seen = {}, {}
    for _, variant in ipairs(choices[position]) do
      lookups = lookups + 1
      if lookups > 120 then return {}, {status="query_too_wide", lookups=120} end
      for _, id in ipairs(self.prefixes[#parts .. ":" .. position .. ":" .. variant.code] or {}) do
        if not seen[id] then seen[id] = true; ids[#ids + 1] = id end
      end
    end
    if not smallest or #ids < #smallest then smallest = ids end
  end
  local out = {}
  for candidate, id in ipairs(smallest or {}) do
    if candidate > 120 then break end
    local row, cost, exact, matches = self.rows[id], 0, true, true
    for position, alternatives in ipairs(choices) do
      local best
      for _, variant in ipairs(alternatives) do
        local alias=self.aliases[self.chars[id][position]]
        if (row.codes[position]:sub(1, #variant.code) == variant.code or alias and alias:sub(1,#variant.code)==variant.code) and
           (not best or variant.cost < best) then best = variant.cost end
      end
      if not best then matches = false; break end
      cost = cost + best
      local alias=self.aliases[self.chars[id][position]]
      exact = exact and (#row.codes[position] == #parts[position] or alias and #alias == #parts[position])
    end
    if matches then
      local tier = cost > 0 and 3 or (wildcard and 2 or (exact and 0 or 1))
      out[#out + 1] = {text=row.text, codes=row.codes, tier=tier,
                      score=(row.weight or 1) + math.min(3, (usage and usage[row.text] or 0) * 0.4) - cost}
    end
  end
  table.sort(out, function(a, b)
    if a.tier ~= b.tier then return a.tier < b.tier end
    if a.score ~= b.score then return a.score > b.score end
    return a.text < b.text
  end)
  return out, {status=#(smallest or {}) > 120 and "query_too_wide" or "ok", lookups=lookups}
end

return M
