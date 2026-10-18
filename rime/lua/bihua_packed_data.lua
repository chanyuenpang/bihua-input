-- Compact immutable backing strings keep old librime-lua full GC affordable.
-- Decoded groups are bounded; eviction never changes source order or values.
local M = {}
local function proxy(backing, decode)
  local cache, queue = {}, {}
  return setmetatable({}, {__index=function(_, key)
    if cache[key] then return cache[key] end
    local value = backing[key]
    if not value then return nil end
    local rows = decode(value)
    cache[key] = rows; queue[#queue+1] = key
    if #queue > 64 then cache[table.remove(queue, 1)] = nil end
    return rows
  end})
end
function M.prefixes(backing)
  return proxy(backing, function(value)
    local rows = {}
    for text, score, exact in value:gmatch("([^\t\n]+)\t([^\t\n]+)\t([^\n]+)\n") do
      rows[#rows+1] = {text, tonumber(score), tonumber(exact)}
    end
    return rows
  end)
end
function M.associations(backing)
  return proxy(backing, function(value)
    local rows = {}
    for text, weight in value:gmatch("([^\t\n]+)\t([^\n]+)\n") do
      rows[#rows+1] = {suffix=text, weight=tonumber(weight)}
    end
    return rows
  end)
end
function M.tails(backing)
  return proxy(backing, function(groups)
    local out = {}
    for length, value in pairs(groups) do
      local rows = {}
      for text, weight, codes in value:gmatch("([^\t\n]+)\t([^\t\n]+)\t([^\n]+)\n") do
        rows[#rows+1] = {text, tonumber(weight), codes}
      end
      out[length] = rows
    end
    return out
  end)
end
return M
