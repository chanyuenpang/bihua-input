#pragma once
#include <cstdint>

// One pending intent, bound to the focus generation that produced its pixels.
struct BihuaMouseState {
  static constexpr int Candidate = 18;
  uint32_t session = 0, generation = 0, serial = 0;
  uint32_t token = 0, pending_session = 0, pending_generation = 0;
  uint64_t projection = 1, pending_projection = 0;
  int candidate_index = -1;
  int action = -1;
  bool executed = false;
  uint64_t queued_at = 0;
  void Focus(uint32_t id) {
    session = id; ++generation; ++projection; Reset();
  }
  void Blur(uint32_t id) { if (session == id) Focus(0); }
  void Reset() { token = 0; action = -1; candidate_index = -1; executed = false; }
  void InvalidateProjection() { ++projection; }
  uint32_t Queue(int intent, uint64_t now, uint32_t displayed_generation,
                 uint64_t displayed_projection = 0, int absolute_index = -1) {
    if (displayed_generation != generation || !session || token || intent < 0 || intent > Candidate ||
        (displayed_projection && displayed_projection != projection) ||
        (intent == Candidate && (absolute_index < 0 || !displayed_projection))) return 0;
    serial = (serial + 1) & 0x7fffffff;
    if (!serial) ++serial;
    token = serial; action = intent; pending_session = session;
    pending_generation = generation; queued_at = now; executed = false;
    pending_projection = projection; candidate_index = absolute_index;
    return token;
  }
  uint32_t Take(uint32_t id) const {
    return id == session && id == pending_session && !executed ? token : 0;
  }
  int Execute(uint32_t id, uint32_t value, uint64_t now) {
    if (!value || value != token || id != session || id != pending_session ||
        generation != pending_generation || projection != pending_projection || executed || now - queued_at > 3000) return -1;
    executed = true; return action;
  }
  bool Finish(uint32_t id, uint32_t value) {
    if (!value || value != token || id != pending_session) return false;
    if (!executed) session = 0;
    Reset(); return true;
  }
};
