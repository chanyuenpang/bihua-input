#pragma once
#include <windows.h>
#include <bcrypt.h>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <vector>
#pragma comment(lib,"bcrypt.lib")

// The installer and settings use the same checked, single-default-code TSV.
class BihuaStrokeInfo {
 public:
  bool available=false;
  std::map<std::wstring,std::string> codes;
  static std::wstring Wide(const std::string& bytes){
    int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,bytes.data(),static_cast<int>(bytes.size()),nullptr,0);
    if(!size)return {};
    std::wstring value(size,L' ');
    MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,bytes.data(),static_cast<int>(bytes.size()),value.data(),size);
    return value;
  }
  static std::vector<std::wstring> Characters(const std::wstring& text){
    std::vector<std::wstring> result;
    for(size_t i=0;i<text.size();++i){size_t count=1;
      if(text[i]>=0xd800&&text[i]<=0xdbff&&i+1<text.size()&&text[i+1]>=0xdc00&&text[i+1]<=0xdfff)count=2;
      result.push_back(text.substr(i,count));i+=count-1;
    }
    return result;
  }
  void Load(const std::filesystem::path& folder){
    available=false;codes.clear();
    auto path=folder/L"current-canonical_strokes.tsv";
    std::error_code error;
    bool current=std::filesystem::exists(path,error);if(error)return;
    if(!current)path=folder/L"canonical_strokes.tsv";
    auto size=std::filesystem::file_size(path,error);if(error||size>32*1024*1024)return;
    auto checksum=path;checksum.replace_extension(L".sha256");
    std::ifstream input(path,std::ios::binary),check(checksum);
    if(!input||!check)return;
    std::string bytes((std::istreambuf_iterator<char>(input)),{}),expected;check>>expected;
    if(bytes.size()>32*1024*1024||expected.size()!=64)return;
    unsigned char digest[32]{};
    BCRYPT_ALG_HANDLE algorithm{};
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)return;
    BCRYPT_HASH_HANDLE hash{};
    auto status=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0);
    if(status>=0)status=BCryptHashData(hash,reinterpret_cast<PUCHAR>(bytes.data()),static_cast<ULONG>(bytes.size()),0);
    if(status>=0)status=BCryptFinishHash(hash,digest,32,0);
    if(hash)BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm,0);
    if(status<0)return;
    std::string actual;for(auto value:digest){actual+="0123456789abcdef"[value>>4];actual+="0123456789abcdef"[value&15];}
    if(actual!=expected)return;
    size_t start=bytes.find('\n');if(start==std::string::npos)return;
    while(++start<bytes.size()){
      size_t end=bytes.find('\n',start);if(end==std::string::npos)end=bytes.size();
      auto line=bytes.substr(start,end-start);if(!line.empty()&&line.back()=='\r')line.pop_back();
      if(!line.empty()){
        size_t tab=line.find('\t');if(tab==std::string::npos){codes.clear();return;}
        auto character=Wide(line.substr(0,tab));auto code=line.substr(tab+1);
        if(Characters(character).size()!=1||code.empty()||code.size()>64||code.find_first_not_of("12345")!=std::string::npos||codes.count(character)){codes.clear();return;}
        codes.emplace(character,code);
      }
      if(end==bytes.size())break;start=end;
    }
    available=!codes.empty();
  }
  std::vector<std::pair<std::wstring,std::string>> Describe(const std::wstring& text) const{
    if(!available)return {{L"笔画信息不可用",""}};
    std::vector<std::pair<std::wstring,std::string>> rows;
    for(auto& character:Characters(text)){
      auto item=codes.find(character);
      rows.emplace_back(character,item==codes.end()?"":item->second);
    }
    return rows;
  }
};
