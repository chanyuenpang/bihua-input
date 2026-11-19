local Json = require('bihua_json')
local M = {}
local completed
function M.run()
  if completed then return completed end
  local sample = Json.encode({text='汉字"\\\n\t',score=12}) .. '\n'
  local payload = string.rep(sample, 14000)
  local envelope = Json.encode({format=1,payload=payload,revision=1})
  local started = os.clock()
  local decoded = Json.decode(envelope)
  local elapsed = os.clock()-started
  assert(decoded.payload==payload and decoded.format==1 and decoded.revision==1,
         'Large escaped snapshot changed during decoding')
  assert(elapsed<2, string.format('Escaped snapshot decode blocks input: %.3fs for %d bytes',elapsed,#envelope))
  assert(Json.decode('"\\u6c49\\u5b57"')=='汉字')
  assert(Json.decode('"\\ud83d\\ude00"')==utf8.char(0x1f600))
  assert(Json.decode('""')=='')
  for _,invalid in ipairs({'"\\x"','"\\u12"','"unterminated','"a\nb"'}) do
    assert(not pcall(Json.decode,invalid),'Malformed JSON accepted: '..invalid)
  end
  completed=string.format('PASS: %d bytes decoded exactly in %.3fs; Unicode and malformed strings checked',#envelope,elapsed)
  return completed
end
return M
