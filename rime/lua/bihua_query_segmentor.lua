local M = {}
function M.func(segmentation, env)
  local input = segmentation.input
  if not input:find("[?|]") or input:find("[^hspnz?|]") then return true end
  segmentation:reset_length(0)
  local segment = Segment(0, #input)
  segment.tags = Set({"abc", "bihua_query"})
  segmentation:add_segment(segment)
  return false
end
return M
