#include "BihuaFocusBoundary.h"
extern "C" __declspec(dllexport) void __cdecl ProbeFocusOut(RimeApi* api, RimeSessionId session) {
  BihuaNeutralFocusOut(api, session);
}
