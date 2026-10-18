#pragma once
#include <windows.h>
#include <bcrypt.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#pragma comment(lib,"bcrypt.lib")

// A narrow, reversible retirement of the exact stock executable. Never kill
// applications, edit StartupApproved, or touch unrelated Run values.
class BihuaLegacyStartup {
 public:
  struct Entry {REGSAM view;std::wstring name;DWORD type;std::vector<BYTE> raw;};
  HKEY root=HKEY_LOCAL_MACHINE;
  std::wstring key=L"Software\\Microsoft\\Windows\\CurrentVersion\\Run";
  std::vector<Entry> removed;
  static std::string Hex(const BYTE* bytes,size_t size){std::string out;for(size_t i=0;i<size;++i){out+="0123456789abcdef"[bytes[i]>>4];out+="0123456789abcdef"[bytes[i]&15];}return out;}
  static std::string Hash(const std::vector<BYTE>& data){
    BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE hash{};BYTE digest[32]{};
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)return {};
    auto status=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0);
    if(status>=0)status=BCryptHashData(hash,const_cast<BYTE*>(data.data()),static_cast<ULONG>(data.size()),0);
    if(status>=0)status=BCryptFinishHash(hash,digest,32,0);
    if(hash)BCryptDestroyHash(hash);BCryptCloseAlgorithmProvider(algorithm,0);
    return status>=0?Hex(digest,32):std::string{};
  }
  static bool Match(DWORD type,const std::vector<BYTE>& raw,const std::wstring& expected){
    if((type!=REG_SZ&&type!=REG_EXPAND_SZ)||raw.size()<2||raw.size()%2)return false;
    std::wstring value(raw.size()/2,L' ');memcpy(value.data(),raw.data(),raw.size());
    if(value.back()!=L'\0'||value.find(L'\0')!=value.size()-1)return false;
    value.pop_back();if(value.size()>1&&value.front()==L'"'&&value.back()==L'"')value=value.substr(1,value.size()-2);
    // Unknown wrappers, environment expansion, parameters or trailing whitespace
    // are intentionally left to the administrator.
    auto normalized=expected;
    for(auto& ch:value)if(ch==L'/')ch=L'\\';
    for(auto& ch:normalized)if(ch==L'/')ch=L'\\';
    return !_wcsicmp(value.c_str(),normalized.c_str());
  }
  LONG Retire(const std::filesystem::path& backup,const std::wstring& executable){
    std::vector<Entry> found;
    for(auto view:{KEY_WOW64_64KEY,KEY_WOW64_32KEY}){
      HKEY handle{};LONG status=RegOpenKeyExW(root,key.c_str(),0,KEY_QUERY_VALUE|KEY_SET_VALUE|view,&handle);
      if(status==ERROR_FILE_NOT_FOUND)continue;if(status)return status;
      for(DWORD index=0;;++index){
        wchar_t name[16384]{};DWORD name_size=16384,type=0,size=65536;std::vector<BYTE> bytes(size);
        status=RegEnumValueW(handle,index,name,&name_size,nullptr,&type,bytes.data(),&size);
        if(status==ERROR_NO_MORE_ITEMS)break;
        if(status==ERROR_MORE_DATA)continue;
        if(status){RegCloseKey(handle);return status;}
        bytes.resize(size);if(Match(type,bytes,executable))found.push_back({static_cast<REGSAM>(view),std::wstring(name,name_size),type,std::move(bytes)});
      }
      RegCloseKey(handle);
    }
    std::error_code error;if(!found.empty())std::filesystem::create_directories(backup,error);if(error)return error.value();
    for(auto& entry:found){
      HKEY handle{};LONG status=RegOpenKeyExW(root,key.c_str(),0,KEY_QUERY_VALUE|KEY_SET_VALUE|entry.view,&handle);if(status)return status;
      DWORD type=0,size=static_cast<DWORD>(entry.raw.size());std::vector<BYTE> current(size);
      status=RegQueryValueExW(handle,entry.name.c_str(),nullptr,&type,current.data(),&size);
      if(status||type!=entry.type||size!=entry.raw.size()||current!=entry.raw){RegCloseKey(handle);continue;}
      auto digest=Hash(entry.raw);if(digest.empty()){RegCloseKey(handle);return ERROR_CRC;}
      auto name=Hex(reinterpret_cast<const BYTE*>(entry.name.data()),entry.name.size()*2);
      auto file=backup/(std::to_string(entry.view)+"-"+name+"-"+digest+".json");
      std::string bytes="{\"format\":1,\"hive\":\"HKLM\",\"view\":"+std::to_string(entry.view)+",\"key\":\"Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run\",\"name_utf16_hex\":\""+name+"\",\"type\":"+std::to_string(entry.type)+",\"data_hex\":\""+Hex(entry.raw.data(),entry.raw.size())+"\",\"sha256\":\""+digest+"\"}\n";
      if(!std::filesystem::exists(file)){
        HANDLE output=CreateFileW(file.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(output==INVALID_HANDLE_VALUE){RegCloseKey(handle);return GetLastError();}
        DWORD written=0;bool saved=WriteFile(output,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr)&&written==bytes.size()&&FlushFileBuffers(output);
        CloseHandle(output);if(!saved){RegCloseKey(handle);return ERROR_WRITE_FAULT;}
      }
      std::ifstream check(file,std::ios::binary);std::string saved((std::istreambuf_iterator<char>(check)),{});
      if(saved!=bytes){RegCloseKey(handle);return ERROR_WRITE_FAULT;}
      // Recheck after backup; never delete an administrator's intervening edit.
      size=static_cast<DWORD>(entry.raw.size());status=RegQueryValueExW(handle,entry.name.c_str(),nullptr,&type,current.data(),&size);
      if(!status&&type==entry.type&&size==entry.raw.size()&&current==entry.raw){
        status=RegDeleteValueW(handle,entry.name.c_str());if(!status)removed.push_back(entry);
      }else status=ERROR_SUCCESS;
      RegCloseKey(handle);if(status)return status;
    }
    return ERROR_SUCCESS;
  }
  LONG Rollback(){
    LONG result=ERROR_SUCCESS;
    for(auto it=removed.rbegin();it!=removed.rend();++it){
      HKEY handle{};LONG status=RegOpenKeyExW(root,key.c_str(),0,KEY_QUERY_VALUE|KEY_SET_VALUE|it->view,&handle);
      if(status){result=status;continue;}
      DWORD size=0;status=RegQueryValueExW(handle,it->name.c_str(),nullptr,nullptr,nullptr,&size);
      if(status==ERROR_FILE_NOT_FOUND)status=RegSetValueExW(handle,it->name.c_str(),0,it->type,it->raw.data(),static_cast<DWORD>(it->raw.size()));
      else if(!status)status=ERROR_ALREADY_EXISTS;
      RegCloseKey(handle);if(status)result=status;
    }
    removed.clear();return result;
  }
};
