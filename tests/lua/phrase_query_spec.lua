local Query = require("bihua_phrase_query")
local M = {}
function M.run()
  local index = Query.new({{text="中国", codes={"szh", "szhhshnh"}, weight=10},
                           {text="中文", codes={"szh", "nhpn"}, weight=9}})
  assert(index:query("sz|szh", true)[1].text == "中国")
  assert(index:query("s?h|sz?h", true)[1].text == "中国")
  assert(index:query("zsh|szh", true)[1].text == "中国", "Adjacent exchange missing")
  assert(#index:query("z?h|szh", true) == 0, "Wildcard also applied adjacent exchange")
  assert(#index:query("sz|szh|h", true) == 0, "Unknown phrase was synthesized")
  assert(not Query.parse("?"))
  assert(not Query.parse("sz||szh"))
  assert(not Query.parse("sz|szh|h|h|h"))
  assert(not Query.parse("s??|s?h"))
  assert(not Query.parse(string.rep("h", 25) .. "|h"))
  local _, diag = index:query("s?h|sz?h", true)
  assert(diag.lookups <= 120)
  return "PASS: phrase prefixes, exact one-stroke wildcard, bounded expansion, no wildcard/swap stacking, syntax limits, no Cartesian words"
end
return M
