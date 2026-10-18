#pragma once
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <future>
#include <chrono>
#include <string>
#include <algorithm>
#include "BihuaStrokeInfo.h"

// UI-thread draft owner. Only the existing Python transaction writes aliases.
class BihuaPersonalRecorder {
 public:
  enum View { Normal, Offer, Draft };
  View view=Normal;
  std::wstring character,error;
  std::string code,system_code;
  enum class GuideRole { Reference, Unchanged, Changed };
  struct GuideStroke {int index;GuideRole role;};
  std::vector<GuideStroke> Guide() const {
    std::vector<GuideStroke> result;
    for(size_t i=0;i<(std::max)(code.size(),system_code.size());++i){
      bool entered=i<code.size();char value=entered?code[i]:system_code[i];
      auto role=!entered?GuideRole::Reference:i<system_code.size()&&code[i]==system_code[i]?GuideRole::Unchanged:GuideRole::Changed;
      result.push_back({static_cast<int>(std::string("hspnz").find(value)),role});
    }
    return result;
  }
  bool clipboard=false,selection=false,replaced=false,busy=false;
  uint64_t draft=0,observed=0;
  std::filesystem::path user,app;
  std::future<std::pair<uint64_t,bool>> job;
  static bool SingleHan(const std::wstring& text){
    if(text.empty()||text.size()>2)return false;
    uint32_t cp=text[0];
    if(cp>=0xd800&&cp<=0xdbff){
      if(text.size()!=2||text[1]<0xdc00||text[1]>0xdfff)return false;
      cp=0x10000+((cp-0xd800)<<10)+(text[1]-0xdc00);
    }else if(text.size()!=1)return false;
    return (cp>=0x3400&&cp<=0x9fff)||(cp>=0xf900&&cp<=0xfaff)||(cp>=0x20000&&cp<=0x323af);
  }
  static std::wstring FromScalar(uint32_t cp){
    if(cp<0x10000)return std::wstring(1,static_cast<wchar_t>(cp));
    if(cp>0x10ffff)return {};
    cp-=0x10000;return {static_cast<wchar_t>(0xd800+(cp>>10)),static_cast<wchar_t>(0xdc00+(cp&1023))};
  }
  bool Observe(const std::wstring& text,uint64_t generation){
    if(!SingleHan(text)||generation==observed||view==Draft)return false;
    observed=generation;character=text;code.clear();system_code.clear();error.clear();view=Offer;return true;
  }
  void Begin(){
    if(view!=Offer)return;
    ++draft;view=Draft;code.clear();error.clear();replaced=false;
    system_code.clear();BihuaStrokeInfo standard;standard.Load(app/L"data");
    auto original=standard.codes.find(character);
    if(standard.available&&original!=standard.codes.end())
      for(char value:original->second)system_code+="hspnz"[value-'1'];
    auto path=user/L"bihua_personal_strokes.tsv";std::error_code ec;
    auto size=std::filesystem::file_size(path,ec);if(ec||size>4194304)return;
    std::ifstream file(path,std::ios::binary);std::string line;
    while(std::getline(file,line)){
      if(!line.empty()&&line.back()=='\r')line.pop_back();
      auto tab=line.find('\t');if(tab==std::string::npos)continue;
      if(BihuaStrokeInfo::Wide(line.substr(0,tab))!=character)continue;
      auto value=line.substr(tab+1);
      if(!value.empty()&&value.size()<=52&&value.find_first_not_of("hspnz")==std::string::npos){code=value;replaced=true;}
      break;
    }
  }
  void Cancel(){if(busy)return;++draft;view=Normal;character.clear();code.clear();system_code.clear();error.clear();}
  void Stroke(int index){if(view==Draft&&!busy&&index>=0&&index<5&&code.size()<52){code+="hspnz"[index];error.clear();}}
  void Backspace(){if(view==Draft&&!busy&&!code.empty()){code.pop_back();error.clear();}}
  static std::wstring Quote(const std::wstring& text){
    std::wstring result=L"\"";size_t slashes=0;
    for(auto c:text){if(c==L'\\'){++slashes;continue;}if(c==L'\"'){result.append(slashes*2+1,L'\\');result+=c;slashes=0;continue;}result.append(slashes,L'\\');slashes=0;result+=c;}
    result.append(slashes*2,L'\\');return result+L"\"";
  }
  void Save(){
    if(view!=Draft||busy||code.empty()||user.empty()||app.empty())return;
    auto id=draft;auto directory=user;auto package=app;auto text=character;auto packed=code;
    busy=true;error.clear();
    job=std::async(std::launch::async,[id,directory,package,text,packed](){
      wchar_t temporary[32768]{},receipt[32768]{};
      if(!GetTempPathW(32768,temporary)||!GetTempFileNameW(temporary,L"bhs",0,receipt))return std::make_pair(id,false);
      auto python=(package/L"python/python.exe").wstring();
      auto script=(package/L"scripts/Manage-Personal.py").wstring();
      std::wstring cmd=Quote(python)+L" -X utf8 -B "+Quote(script)+L" strokes upsert --rime-dir "+Quote(directory.wstring())+
          L" "+Quote(L"--char="+text)+L" "+Quote(L"--codes="+std::wstring(packed.begin(),packed.end()))+L" --result-file "+Quote(receipt);
      STARTUPINFOW si{sizeof(si)};si.dwFlags=STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;PROCESS_INFORMATION process{};
      bool success=false;
      if(CreateProcessW(python.c_str(),cmd.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,package.c_str(),&si,&process)){
        // The data command is bounded and owns no desktop interaction. Never
        // terminate it during an atomic write; wait on this worker only.
        WaitForSingleObject(process.hProcess,INFINITE);DWORD exit=1;GetExitCodeProcess(process.hProcess,&exit);
        if(exit==0){std::ifstream file{std::filesystem::path(receipt)};std::string data((std::istreambuf_iterator<char>(file)),{});success=data.find("\"status\": \"applied\"")!=std::string::npos;}
        CloseHandle(process.hThread);CloseHandle(process.hProcess);
      }
      DeleteFileW(receipt);return std::make_pair(id,success);
    });
  }
  bool Poll(){
    if(!busy||!job.valid()||job.wait_for(std::chrono::milliseconds(0))!=std::future_status::ready)return false;
    auto result=job.get();busy=false;
    if(result.first!=draft)return false;
    if(result.second)Cancel();else error=L"保存失败，请重试";
    return true;
  }
};
