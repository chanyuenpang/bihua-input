-- One owner per path, native LevelDB process lock, and recoverable same-directory
-- snapshot replacement. JSON codec is vendored rxi/json.lua (MIT).
local Core = require("bihua_association_core")
local Json = require("bihua_json")
local M = {}
local owners = {}

local function checksum(text)
  local hash = 2166136261
  for i = 1, #text do hash = ((hash ~ text:byte(i)) * 16777619) & 0xffffffff end
  return string.format("%08x", hash)
end

local function read_bytes(path)
  local file, message, code = io.open(path, "rb")
  if not file then return nil, code == 2 and "missing" or message end
  local bytes = file:read("*a")
  file:close()
  if not bytes then return nil, "read_failed" end
  return bytes
end

local function read(path)
  local bytes, error = read_bytes(path)
  if not bytes then return nil, error end
  local ok, envelope = pcall(Json.decode, bytes)
  if not ok or type(envelope) ~= "table" or envelope.format ~= 1 or type(envelope.payload) ~= "string" or
     checksum(envelope.payload) ~= envelope.checksum or type(envelope.revision) ~= "number" or
     envelope.revision < 1 or envelope.revision % 1 ~= 0 then
    return nil, "invalid_snapshot"
  end
  local decoded, snapshot = pcall(Json.decode, envelope.payload)
  if not decoded then return nil, "invalid_payload" end
  local valid = pcall(Core.restore, snapshot)
  if not valid then return nil, "invalid_personal_state" end
  return {snapshot=snapshot, revision=envelope.revision, bytes=bytes}
end

local function acquire_lock(path)
  -- Rime's native LevelDB holds its OS lock until close/process exit. The lock
  -- covers reading, recovery, and every save; revision checks alone are not CAS.
  -- Only the lock database lives here: personal content stays in the snapshot.
  -- UserDb is scoped to Rime's user directory already. Hash the ASCII basename:
  -- older Windows Rime exposes user_dir in the ANSI codepage rather than UTF-8.
  local normalized = path:gsub("\\", "/"):match("[^/]+$"):lower()
  local name = "bihua_association_lock_" .. checksum(normalized)
  local ok, db = pcall(function() return UserDb(name, "userdb") end)
  if not ok or not db then return nil, "lock_unavailable" end
  local opened, success = pcall(function() return db:open() end)
  if not opened or not success then return nil, "lock_busy_or_unavailable" end
  return db
end

function M.open(path)
  if owners[path] then return owners[path] end
  local lock, lock_error = acquire_lock(path)
  if not lock then
    local owner = {path=path, revision=0, state=Core.new(1000), read_only=true,
                   status=lock_error}
    owner.last_snapshot = owner.state:snapshot()
    owners[path] = owner
    return owner
  end
  local data, error = read(path)
  local recovered = false
  if not data and error == "missing" then
    local backup, backup_error = read(path .. ".previous")
    if backup then data, recovered = backup, true
    elseif backup_error ~= "missing" then error = backup_error end
  end
  local owner = {path=path, lock=lock, revision=data and data.revision or 0, recovered=recovered,
                 disk_bytes=data and data.bytes or nil,
                 state=data and Core.restore(data.snapshot) or Core.new(1000),
                 status=data and (recovered and "recovered_backup" or "ok") or
                        (error == "missing" and "new" or "read_failed:" .. tostring(error))}
  owner.last_snapshot = data and data.snapshot or owner.state:snapshot()
  owner.read_only = not data and error ~= "missing"
  owners[path] = owner
  if owner.state.migration_required and not owner.read_only then
    local saved, reason = M.save(owner)
    if not saved then
      owner.read_only = true
      owner.status = "migration_failed:" .. tostring(reason)
    else owner.state.migration_required = nil end
  end
  return owner
end

local function fail(owner, reason)
  owner.status = reason
  local previous = owner.state
  owner.state = Core.restore(owner.last_snapshot, {clock=previous.clock, migration_now=previous.migration_now})
  -- Session context is not learned data: keep the already committed text so
  -- typing can continue, but discard all unpersisted observations/confirmations.
  owner.state.context = previous.context
  owner.state.segment = math.max(owner.state.segment, previous.segment + 1)
  owner.state.revision = previous.revision + 1
  return false, reason
end

function M.save(owner)
  if owner.read_only or not owner.lock then return fail(owner, owner.status) end
  -- Under the native process lock, compare the exact last validated/written
  -- bytes. Re-parsing and rebuilding all indices on every commit blocks input.
  -- External edits, including same-revision changes, still fail closed.
  local disk, error = read_bytes(owner.path)
  if disk and disk ~= owner.disk_bytes then return fail(owner, "write_conflict") end
  if not disk and error ~= "missing" then return fail(owner, "read_failed:" .. tostring(error)) end
  if not disk and owner.revision ~= 0 and not owner.recovered then return fail(owner, "write_conflict") end
  local snapshot = owner.state:snapshot()
  local payload = Json.encode(snapshot)
  local envelope = Json.encode({format=1, revision=owner.revision + 1,
                                payload=payload, checksum=checksum(payload)}) .. "\n"
  local temporary, backup = owner.path .. ".pending", owner.path .. ".previous"
  local file, message = io.open(temporary, "wb")
  if not file then return fail(owner, "write_failed:" .. tostring(message)) end
  local written, write_error = file:write(envelope)
  local flushed, flush_error = file:flush()
  local closed, close_error = file:close()
  if not written or not flushed or not closed then
    return fail(owner, "write_failed:" .. tostring(write_error or flush_error or close_error))
  end
  if disk then
    local previous = io.open(backup, "rb")
    if previous then
      previous:close()
      local removed, remove_error = os.remove(backup)
      if not removed then return fail(owner, "rotate_failed:" .. tostring(remove_error)) end
    end
    local moved, move_error = os.rename(owner.path, backup)
    if not moved then return fail(owner, "rotate_failed:" .. tostring(move_error)) end
  end
  local replaced, replace_error = os.rename(temporary, owner.path)
  if not replaced then
    if disk then os.rename(backup, owner.path) end
    return fail(owner, "replace_failed:" .. tostring(replace_error))
  end
  owner.revision = owner.revision + 1
  owner.disk_bytes = envelope
  owner.last_snapshot = snapshot
  owner.recovered, owner.status = false, "ok"
  return true
end

-- Exposed for offline management/verification of the exact same file envelope.
M.read = read
M.checksum = checksum
return M
