#include "BihuaNumLock.h"
#include <cassert>
#include <cstdio>
int main(){
  for(bool original:{false,true}){
    BihuaNumLockPolicy policy;
    assert(policy.Lease(true,original)==(original?0:1));
    assert(policy.Lease(true,true)==0);
    for(int i=0;i<10;++i){
      assert(policy.Key(true,true)==2);
      assert(policy.Key(true,true)==1);
      assert(policy.Key(false,true)==1);
    }
    assert(policy.Lease(false,true)==(original?0:-1));
    assert(policy.Key(true,false)==0&&policy.Key(false,false)==0);
    assert(policy.Lease(false,original)==0);
  }
  BihuaNumLockPolicy boundary;
  boundary.Lease(true,true);assert(boundary.Key(true,true)==2);
  assert(boundary.Key(false,false)==1);
  boundary.Lease(false,true);assert(boundary.Key(true,false)==0);
  assert(boundary.Key(false,true)==0);
  std::puts("PASS: original on/off, guarded repeats, restore, inactive pass-through, focus-boundary releases; no OS input injected");
}
