-- Reorder the actual simplified, deduplicated menu without adding candidates.
local M = {}
function M.func(input, env)
  local ctx = env.engine.context
  if ctx:get_property("bihua_feedback_session") ~= "" then
    require("bihua_association_runtime").filter(input, ctx)
  else
    for candidate in input:iter() do yield(candidate) end
  end
end
return M
