#pragma once
#include <rime_api.h>
inline void BihuaNeutralFocusOut(RimeApi* api, RimeSessionId session) {
  if (!session || !api->find_session(session)) return;
  // Clear held keypad selection even when personal association is disabled.
  api->set_property(session, "bihua_keymap_reset", "focus_out");
  char symbols[8]{};
  api->get_property(session,"bihua_symbol_active",symbols,sizeof(symbols));
  if(symbols[0]=='1'){
    api->set_property(session,"bihua_mouse_action","symbol_cancel");
    api->process_key(session,0xffd5,0);
    api->set_property(session,"bihua_mouse_action","");
  }
  char owner[256]{};
  api->get_property(session, "bihua_feedback_session", owner, sizeof(owner));
  if (!owner[0]) return;
  api->set_property(session, "bihua_feedback_neutral_boundary", "focus_out");
  char active[8]{};
  api->get_property(session, "bihua_prediction_menu_active", active, sizeof(active));
  if (active[0] != '1' || active[1] != '\0') return;
  RIME_STRUCT(RimeContext, context);
  if (api->get_context(session, &context)) {
    bool prediction = context.composition.length == 0 && context.menu.num_candidates > 0;
    api->free_context(&context);
    if (prediction) api->clear_composition(session);
  }
}
