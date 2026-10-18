local Store = require("bihua_association_store")
local Core = require("bihua_association_core")
local Json = require("bihua_json")
local M = {}
local completed = {}
local function read_bytes(path)
  local file = assert(io.open(path, "rb"))
  local bytes = file:read("*a")
  file:close()
  return bytes
end
local function write_bytes(path, bytes)
  local file = assert(io.open(path, "wb"))
  assert(file:write(bytes)); assert(file:close())
end
function M.run(directory)
  if completed[directory] then return completed[directory] end
  local path = directory .. "/store-fixture.jsonl"
  local owner = Store.open(path)
  assert(owner.lock and not owner.read_only, "Native process lock unavailable")
  assert(Store.open(path) == owner, "Multiple in-process owners for one personal file")
  owner.state:observe("星", "manual_stroke_char")
  assert(Store.save(owner))
  owner.state:observe("河", "manual_stroke_char")
  assert(Store.save(owner))
  assert(#assert(Store.read(path)).snapshot.window == 2)
  assert(#assert(Store.read(path .. ".previous")).snapshot.window == 1)
  local valid_backup = read_bytes(path .. ".previous")
  local previous_decode = Json.decode
  local decode_calls = 0
  Json.decode = function(...) decode_calls = decode_calls + 1; return previous_decode(...) end
  assert(Store.save(owner))
  Json.decode = previous_decode
  assert(decode_calls == 0, "Every commit re-parsed the validated snapshot")
  write_bytes(path, "1") -- valid JSON, invalid envelope
  owner.state:observe("计", "manual_stroke_char")
  assert(not Store.save(owner), "Corrupted personal data was overwritten")
  assert(read_bytes(path) == "1" and #owner.state.window == 2,
         "Failed save changed existing bytes or falsely retained unsaved history")
  assert(table.concat(owner.state.context) == "星河计",
         "Save failure discarded already committed session context")

  local missing = Store.open(directory .. "/nonexistent-parent/state.jsonl")
  missing.state:observe("甲", "manual_stroke_char")
  assert(not Store.save(missing) and #missing.state.window == 0,
         "Unwritable target falsely reported success")

  local recover_path = directory .. "/recovery-fixture.jsonl"
  write_bytes(recover_path .. ".previous", valid_backup)
  local recovered = Store.open(recover_path)
  assert(recovered.status == "recovered_backup" and #recovered.state.window == 1)
  recovered.state:observe("河", "manual_stroke_char")
  assert(Store.save(recovered) and Store.read(recover_path), "Interrupted replacement did not recover")

  local external = Json.decode(read_bytes(recover_path))
  external.revision = external.revision + 1
  local changed = Json.encode(external)
  write_bytes(recover_path, changed)
  recovered.state:observe("计", "manual_stroke_char")
  local saved, reason = Store.save(recovered)
  assert(not saved and reason == "write_conflict" and read_bytes(recover_path) == changed)

  local same_revision = Store.open(directory .. "/same-revision-fixture.jsonl")
  same_revision.state:observe("甲", "manual_stroke_char"); assert(Store.save(same_revision))
  local same_bytes = read_bytes(same_revision.path)
  write_bytes(same_revision.path, same_bytes .. " ")
  same_revision.state:observe("乙", "manual_stroke_char")
  local same_saved, same_reason = Store.save(same_revision)
  assert(not same_saved and same_reason == "write_conflict")
  assert(read_bytes(same_revision.path) == same_bytes .. " " and #same_revision.state.window == 1,
         "Same-revision external change was overwritten or unsaved state retained")

  -- Disk codec preserves bounded feedback; a failed multi-edge settlement rolls back all scores.
  local scored=Store.open(directory.."/feedback-fixture.jsonl")
  scored.state:observe("甲","manual_stroke_char")
  local offered=scored.state:query(45,{{suffix="乙",weight=2},{suffix="丙",weight=1}})
  assert(scored.state:select(offered[1],true,offered));assert(Store.save(scored))
  assert(scored.state.confirmed["甲乙"].score==11 and scored.state.confirmed["甲丙"].score==9)
  local saved_bytes=read_bytes(scored.path)
  scored.state:boundary();scored.state:observe("甲","manual_stroke_char")
  local fresh=scored.state:query(45,{{suffix="乙",weight=2},{suffix="丙",weight=1}})
  assert(scored.state:select(fresh[1],true,fresh))
  local envelope=Json.decode(saved_bytes);envelope.revision=envelope.revision+1
  local outside=Json.encode(envelope);write_bytes(scored.path,outside)
  assert(not Store.save(scored))
  assert(scored.state.confirmed["甲乙"].score==11 and scored.state.confirmed["甲丙"].score==9,
    "Failed settlement retained only part of the batch")
  assert(read_bytes(scored.path)==outside)
  local restored=Core.restore(assert(Store.read(scored.path)).snapshot,{clock=function() return 999999999 end})
  assert(restored.confirmed["甲乙"].score==11)
  local legacy={version=1,capacity=1000,sequence=2,segment=1,half_life=604800,minimum_weight=.2,maximum_strength=8,window={},
    confirmed={["甲乙"]={count=1,recent=2,strength=1,last_used_at=os.time()}}}
  local payload=Json.encode(legacy)
  local legacy_bytes=Json.encode({format=1,revision=1,payload=payload,checksum=Store.checksum(payload)}).."\n"
  local migration_path=directory.."/migration-fixture.jsonl"
  write_bytes(migration_path,legacy_bytes)
  local migrated=Store.open(migration_path)
  assert(not migrated.read_only and Store.read(migration_path).snapshot.version==2)
  assert(read_bytes(migration_path..".previous")==legacy_bytes)
  assert(migrated.state.confirmed["甲乙"].score>=10)
  local failed_path=directory.."/failed-migration-fixture.jsonl"
  write_bytes(failed_path,legacy_bytes)
  local original_open=io.open
  io.open=function(path,mode)
    if path==failed_path..".pending" then return nil,"denied",13 end
    return original_open(path,mode)
  end
  local denied=Store.open(failed_path)
  io.open=original_open
  assert(denied.read_only and denied.status:find("migration_failed",1,true))
  assert(read_bytes(failed_path)==legacy_bytes)
  completed[directory]="PASS: snapshot/checksum, native lock, previous recovery, failure rollback, atomic multi-edge feedback, v1 migration transaction/failure, no restart/time refresh"
  return completed[directory]
end
return M
