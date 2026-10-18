local Runtime = require("bihua_phrase_runtime")
local M = {}
function M.run()
  local original_open, original_memory = io.open, Memory
  local props = {}
  local env = {engine={schema={config={get_bool=function() return false end}},
    context={set_property=function(_, key, value) props[key]=value end,
             commit_notifier={connect=function() return {disconnect=function() end} end}}}}
  local function open_text(text)
    return {lines=function()
      local position=1
      return function()
        if position>#text then return nil end
        local finish=text:find("\n", position, true) or (#text+1)
        local line=text:sub(position, finish-1); position=finish+1; return line
      end
    end, close=function() end}
  end
  Memory=function() return {finish_session=function() end, disconnect=function() end} end
  local ok, error = pcall(function()
    io.open=function() return open_text("测试\th|s\t1e+09\n") end
    Runtime.init(env)
    assert(props.bihua_phrase_load_status=="ok" and #env.phrase_index.rows==1)
    Runtime.fini(env)
    io.open=function() return open_text("测试\th|s\t1e+09\n坏词\t66|77\t1\n") end
    Runtime.init(env)
    assert(props.bihua_phrase_load_status=="invalid_batch" and #env.phrase_index.rows==1)
    Runtime.fini(env)
    io.open=function() return nil, "permission denied", 13 end
    Runtime.init(env)
    assert(props.bihua_phrase_load_status=="read_failed" and #env.phrase_index.rows==1)
    Runtime.fini(env)
  end)
  io.open, Memory = original_open, original_memory
  assert(ok, error)
  return "PASS: exponent weights, invalid batch, read failure preserves process index"
end
return M
