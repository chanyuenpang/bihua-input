#pragma once
#include <cstdint>

// Observed once across Test/actual callbacks. The host receives Shift events;
// Caps Lock belongs to Windows; English case is a projection of that state.
struct BihuaKeyboardRoute {
  enum Mode : uint32_t { Chinese, EnglishLower, EnglishUpper };
  Mode mode=Chinese;
  bool shift=false,shift_used=false;
  bool caps_known=false,caps_value=false;
  uint32_t shift_key=0;
  bool English() const {return mode!=Chinese;}
  void Toggle(bool caps=false){mode=mode==Chinese?(caps?EnglishUpper:EnglishLower):Chinese;caps_known=true;caps_value=caps;}
  bool Caps(bool caps){
    auto before=mode;
    if(!caps_known||caps_value!=caps){
      caps_known=true;caps_value=caps;
      if(caps)mode=EnglishUpper;else if(mode==EnglishUpper)mode=EnglishLower;
    }
    return mode!=before;
  }
  void Reset(){mode=Chinese;caps_known=false;CancelGesture();}
  void CancelGesture(){shift=false;shift_used=false;shift_key=0;}
  void OtherDown(){if(shift)shift_used=true;}
  bool Shift(uint32_t key,bool down,bool chord,bool caps=false){
    if(down){
      if(!shift){shift=true;shift_used=chord;shift_key=key;}
      else if(shift_key!=key)shift_used=true;
      return false;
    }
    bool toggle=shift&&key==shift_key&&!shift_used&&!chord;
    shift=false;shift_used=false;shift_key=0;
    if(toggle)Toggle(caps);
    return toggle;
  }
};
