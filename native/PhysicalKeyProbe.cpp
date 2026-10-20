#include "BihuaPersonalKeys.h"
#include <cassert>
#include <iostream>
#include <map>

int main(){
  using Key=BihuaPhysicalKey;
  assert(sizeof(BihuaPhysicalEventV1)==28);
  auto fn=Key::Parse("win-v1:63:0:ff");assert(fn.kind==Key::Physical&&!fn.Reserved());
  BihuaPhysicalEventV1 event;event.vk=0xff;event.scan=0x63;assert(event.Valid()&&fn.Matches(event));
  event.vk=0x07;assert(fn.Matches(event));event.flags=1;assert(!fn.Matches(event));
  auto weak=Key::Parse("win-v1:00:0:ff");event.vk=0xff;event.scan=0;event.flags=0;assert(weak.Matches(event));
  event.vk=0xfe;assert(!weak.Matches(event));event.scan=0x63;assert(!weak.Matches(event));
  assert(Key::Parse("win-v1:53:0:2e").Virtual()==VK_DECIMAL);
  assert(Key::Parse("win-v1:53:1:2e").Virtual()==VK_DELETE);
  assert(Key::Parse("win-v1:53:0:2e").Overlaps(Key::Parse("KP_Decimal")));
  assert(!Key::Parse("win-v1:53:1:2e").Overlaps(Key::Parse("KP_Decimal")));
  assert(Key::Normalize(VK_UP,0x48,false)==VK_NUMPAD8);
  assert(Key::Normalize(VK_UP,0x48,true)==VK_UP);
  assert(Key::Normalize(VK_DELETE,0x53,false)==VK_DECIMAL);
  assert(Key::Normalize(VK_INSERT,0x52,false)==VK_NUMPAD0);
  for(auto text:{"win-v1:00:0:00","win-v1:63:2:ff","win-v1:63:0:ffjunk","unknown"})assert(Key::Parse(text).kind==Key::Invalid);
  for(auto text:{"win-v1:2a:0:a0","win-v1:36:0:a1","win-v1:1d:1:a3","win-v1:38:0:a4","win-v1:3a:0:14","win-v1:1c:1:0d","Escape"})assert(Key::Parse(text).Reserved());
  std::map<std::string,std::string> config;
  const char* actions[]={"h","s","p","n","z","wildcard","separator"};
  const char* letters[]={"h","s","p","d","z","t","f"};
  const char* keypad[]={"KP_7","KP_8","KP_9","KP_4","KP_5","KP_6","KP_Decimal"};
  for(int i=0;i<7;++i){config[std::string("bihua_keys/letter/")+actions[i]]=letters[i];config[std::string("bihua_keys/keypad/")+actions[i]]=keypad[i];}
  config["bihua_keys/letter_style"]="standard";config["bihua_keys/symbol_toggle"]="Num_Lock";
  auto read=[&](const std::string& name){return config[name];};
  auto map=BihuaPersonalKeyMap::Read(read);assert(map.valid&&map.UsesVirtual(VK_DECIMAL));
  config["bihua_keys/keypad/h"]="win-v1:63:0:ff";map=BihuaPersonalKeyMap::Read(read);assert(map.valid);
  event=BihuaPhysicalEventV1{};event.vk=0xff;event.scan=0x63;assert(map.Resolve(event)==0);
  KBDLLHOOKSTRUCT key{};key.vkCode=event.vk;key.scanCode=event.scan;assert(map.Action(key)==0);
  BihuaPersonalKeyCapture::Ledger ledger;int action=-1;
  assert(ledger.Route(key,true,true,map,action)&&action==0);
  assert(ledger.Route(key,true,true,map,action)&&action==-1);
  assert(ledger.Route(key,false,false,map,action)&&!ledger.Any());
  config["bihua_keys/keypad/h"]="win-v1:1f:0:53";assert(!BihuaPersonalKeyMap::Read(read).valid);
  config["bihua_keys/keypad/h"]="win-v1:45:1:90";assert(!BihuaPersonalKeyMap::Read(read).valid);
  config["bihua_keys/symbol_toggle"]="";assert(BihuaPersonalKeyMap::Read(read).valid);
  config["bihua_keys/keypad/h"]="";config["bihua_keys/letter/s"]="";
  map=BihuaPersonalKeyMap::Read(read);assert(map.valid&&!map.UsesVirtual(VK_NUMPAD7));
  event.version=2;assert(!event.Valid());event.version=1;event.size=24;assert(!event.Valid());
  std::cout<<"{\"result\":\"PASS\",\"physical_identity\":true,\"normal_and_draft_resolver\":true,\"unknown_vk_scan\":true,\"repeat_release\":true,\"global_conflicts\":true,\"numlock_override\":true,\"abi_bytes\":28,\"vectors\":[";
  bool comma=false;
  for(auto token:{"win-v1:63:0:ff","win-v1:00:0:ff","win-v1:53:0:2e","win-v1:53:1:2e","win-v1:2a:0:a0","win-v1:1d:1:a3","win-v1:37:1:2c","F24","KP_Decimal","win-v1:00:0:00"}){
    auto key=Key::Parse(token);if(comma)std::cout<<",";comma=true;
    std::cout<<"{\"token\":\""<<token<<"\",\"valid\":"<<(key.kind!=Key::Invalid?"true":"false")<<",\"reserved\":"<<(key.Reserved()?"true":"false")<<",\"virtual\":"<<key.Virtual()<<"}";
  }
  std::cout<<"]}"<<std::endl;
}
