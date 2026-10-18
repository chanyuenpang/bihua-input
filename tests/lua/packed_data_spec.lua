local Packed = require("bihua_packed_data")
local M = {}
function M.run()
  local prefix, associations, tails = {}, {}, {}
  for i=1, 75 do
    prefix[tostring(i)] = "甲\t" .. i .. "\t1\n乙\t0.5\t0\n"
    associations[tostring(i)] = "甲\t" .. i .. "\n乙\t0.5\n"
    tails[tostring(i)] = {[1]="乙\t" .. i .. "\thsp\n"}
  end
  local p, a, t = Packed.prefixes(prefix), Packed.associations(associations), Packed.tails(tails)
  local old = p["1"]
  for pass=1, 3 do
    for i=1, 75 do
      local key=tostring(i)
      assert(p[key][1][1]=="甲" and p[key][1][2]==i and p[key][2][2]==0.5)
      assert(a[key][1].suffix=="甲" and a[key][1].weight==i)
      assert(t[key][1][1][1]=="乙" and t[key][1][1][2]==i and t[key][1][1][3]=="hsp")
    end
  end
  assert(p["1"]~=old and old[1][2]==1, "Eviction changed an existing returned group")
  assert(not p["missing"])
  return "PASS: packed values/order and repeated cache eviction"
end
return M
