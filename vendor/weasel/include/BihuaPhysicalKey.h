#pragma once
#include <windows.h>
#include <array>
#include <cstdint>
#include <string>

// Fixed-width transport. Session/PID ownership belongs to the pipe request.
struct BihuaPhysicalEventV1 {
  uint32_t version=1,size=28,rime=0,vk=0,scan=0,flags=0,repeat=1;
  enum : uint32_t { Extended=1, Up=2, Previous=4 };
  bool Valid()const{return version==1&&size==sizeof(*this)&&vk<=255&&scan<=255&&(vk||scan)&&!(flags&~7u)&&repeat<=65535;}
};
static_assert(sizeof(BihuaPhysicalEventV1)==28,"Physical event ABI must be identical in 32/64-bit clients");

struct BihuaPhysicalKey {
  enum Kind { Invalid,Legacy,Physical } kind=Invalid;
  uint32_t vk=0,scan=0,extended=0,rime=0;
  std::string name;
  static UINT Normalize(UINT vk,UINT scan,bool extended){
    if(!extended){switch(scan){
      case 0x4f:return VK_NUMPAD1;case 0x50:return VK_NUMPAD2;case 0x51:return VK_NUMPAD3;
      case 0x4b:return VK_NUMPAD4;case 0x4c:return VK_NUMPAD5;case 0x4d:return VK_NUMPAD6;
      case 0x47:return VK_NUMPAD7;case 0x48:return VK_NUMPAD8;case 0x49:return VK_NUMPAD9;
      case 0x52:return VK_NUMPAD0;case 0x53:return VK_DECIMAL;case 0x37:return VK_MULTIPLY;
    }}else if(scan==0x35)return VK_DIVIDE;
    return vk;
  }
  UINT Virtual()const{
    UINT value=vk;
    if(scan){auto mapped=MapVirtualKeyW(scan|(extended?0xe000:0),MAPVK_VSC_TO_VK_EX);if(mapped)value=mapped;}
    return Normalize(value,scan,!!extended);
  }
  bool Reserved()const{
    switch(Virtual()){
      case VK_SHIFT:case VK_LSHIFT:case VK_RSHIFT:case VK_CONTROL:case VK_LCONTROL:case VK_RCONTROL:
      case VK_MENU:case VK_LMENU:case VK_RMENU:case VK_LWIN:case VK_RWIN:case VK_CAPITAL:
      case VK_ESCAPE:case VK_BACK:case VK_TAB:case VK_SPACE:case VK_RETURN:return true;
    }return false;
  }
  static int Hex(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;}
  static BihuaPhysicalKey Parse(const std::string& text){
    BihuaPhysicalKey key;key.name=text;
    if(text.size()==14&&text.substr(0,7)=="win-v1:"&&text[9]==':'&&text[11]==':'&&
       (text[10]=='0'||text[10]=='1')&&Hex(text[7])>=0&&Hex(text[8])>=0&&Hex(text[12])>=0&&Hex(text[13])>=0){
      key.scan=16*Hex(text[7])+Hex(text[8]);key.extended=text[10]-'0';key.vk=16*Hex(text[12])+Hex(text[13]);
      if(key.scan||key.vk)key.kind=Physical;return key;
    }
    if(text.size()==1&&text[0]>='a'&&text[0]<='z'){key.vk=text[0]-'a'+'A';key.rime=text[0];}
    else if(text.size()==4&&text.substr(0,3)=="KP_"&&text[3]>='0'&&text[3]<='9'){
      key.vk=VK_NUMPAD0+text[3]-'0';key.rime=0xffb0+text[3]-'0';
    }else{
      struct Named{const char* name;UINT vk,rime;};
      const Named names[]={{"KP_Divide",VK_DIVIDE,0xffaf},{"KP_Multiply",VK_MULTIPLY,0xffaa},{"KP_Decimal",VK_DECIMAL,0xffae},
        {"KP_Add",VK_ADD,0xffab},{"KP_Subtract",VK_SUBTRACT,0xffad},{"Num_Lock",VK_NUMLOCK,0xff7f},
        {"space",VK_SPACE,0x20},{"Return",VK_RETURN,0xff0d},{"KP_Enter",VK_RETURN,0xff8d},{"Escape",VK_ESCAPE,0xff1b},
        {"BackSpace",VK_BACK,0xff08},{"Tab",VK_TAB,0xff09},{"Left",VK_LEFT,0xff51},{"Right",VK_RIGHT,0xff53},
        {"Up",VK_UP,0xff52},{"Down",VK_DOWN,0xff54}};
      for(const auto& item:names)if(text==item.name){key.vk=item.vk;key.rime=item.rime;break;}
      if(!key.vk&&text.size()>=2&&text.size()<=3&&text[0]=='F'&&text[1]>='1'&&text[1]<='9'){
        int number=text[1]-'0';
        if(text.size()==3){if(text[2]<'0'||text[2]>'9')return key;number=number*10+text[2]-'0';}
        if(number>=1&&number<=24){key.vk=VK_F1+number-1;key.rime=0xffbe + number-1;}
      }
    }
    if(key.vk)key.kind=Legacy;return key;
  }
  bool Overlaps(const BihuaPhysicalKey& other)const{
    if(kind==Legacy&&other.kind==Legacy)return name==other.name;
    if(kind==Physical&&other.kind==Physical)return scan==other.scan&&extended==other.extended&&(scan||vk==other.vk);
    if(kind==Physical&&other.kind==Legacy)return Virtual()==other.vk;
    if(kind==Legacy&&other.kind==Physical)return vk==other.Virtual();
    return false;
  }
  bool Matches(const BihuaPhysicalEventV1& key,bool draft=false)const{
    if(kind==Physical)return extended==!!(key.flags&BihuaPhysicalEventV1::Extended)&&
      (scan?scan==key.scan:!key.scan&&vk==key.vk);
    if(kind==Legacy)return draft?vk==Normalize(key.vk,key.scan,!!(key.flags&BihuaPhysicalEventV1::Extended)):rime==(key.rime&65535);
    return false;
  }
};

// The same immutable compiled-config projection serves normal input and DIY.
struct BihuaPhysicalBindings {
  std::array<BihuaPhysicalKey,7> letters{},keypad{};
  BihuaPhysicalKey symbol;
  bool valid=false,compat_n=false;
  template<class Reader>static BihuaPhysicalBindings Read(Reader read){
    BihuaPhysicalBindings map;const char* actions[]={"h","s","p","n","z","wildcard","separator"};
    std::array<BihuaPhysicalKey,15> claimed{};int count=0;
    auto accept=[&](const BihuaPhysicalKey& key){
      if(key.name.empty())return true; // explicitly unbound by a later assignment
      if(key.kind==BihuaPhysicalKey::Invalid||key.Reserved())return false;
      for(int i=0;i<count;++i)if(key.Overlaps(claimed[i]))return false;
      claimed[count++]=key;return true;
    };
    for(int i=0;i<7;++i){
      map.letters[i]=BihuaPhysicalKey::Parse(read(std::string("bihua_keys/letter/")+actions[i]));
      map.keypad[i]=BihuaPhysicalKey::Parse(read(std::string("bihua_keys/keypad/")+actions[i]));
      if(!accept(map.letters[i])||!accept(map.keypad[i]))return {};
    }
    auto symbol=read("bihua_keys/symbol_toggle");
    if(!symbol.empty()){map.symbol=BihuaPhysicalKey::Parse(symbol);if(!accept(map.symbol))return {};}
    map.compat_n=read("bihua_keys/letter_style")=="standard";map.valid=true;return map;
  }
  int Resolve(const BihuaPhysicalEventV1& key,bool draft=false)const{
    if(!valid||!key.Valid())return -1;
    for(int i=0;i<7;++i)if(letters[i].Matches(key,draft)||keypad[i].Matches(key,draft))return i;
    if(symbol.Matches(key,draft))return 7;
    if(compat_n&&(draft?BihuaPhysicalKey::Normalize(key.vk,key.scan,!!(key.flags&1))=='N':(key.rime&65535)=='n'))return 3;
    return -1;
  }
  bool UsesVirtual(UINT vk)const{
    for(const auto& key:letters)if(key.Virtual()==vk)return true;
    for(const auto& key:keypad)if(key.Virtual()==vk)return true;
    return symbol.kind!=BihuaPhysicalKey::Invalid&&symbol.Virtual()==vk;
  }
};
