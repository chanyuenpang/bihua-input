"""Cross-language raw-key identity, conflict and reserved-control checks."""
from pathlib import Path
import argparse,copy,json,subprocess
import key_bindings as keys
ROOT=Path(__file__).resolve().parent.parent
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--native-probe',type=Path);parser.add_argument('--report',type=Path);args=parser.parse_args()
    settings={'letter_style':'standard','keypad_style':'789456','letter_keys':keys.LETTER['standard'].copy(),'keypad_keys':keys.KEYPAD['789456'].copy(),'symbol_toggle':'Num_Lock'}
    assert keys.validate(settings)==settings
    fn=keys.physical_key(0xff,0x63);changed=copy.deepcopy(settings)
    changed.update(keypad_style='custom');changed['keypad_keys']['h']=fn;assert keys.validate(changed)==changed
    # Main-row digits, function/OEM/unknown VK, extended and scan-less events
    # use the same field, without a device-specific positive allowlist.
    for vk,scan,extended in [(0x31,0x02,False),(0xff,0x63,False),(0xff,0,False),(0xc1,0x70,True),(0x87,0x76,False),(0x2c,0x37,True)]:
        sample=copy.deepcopy(changed);sample['keypad_keys']['h']=keys.physical_key(vk,scan,extended);keys.validate(sample)
    def rejects(sample):
        try:keys.validate(sample)
        except ValueError:return
        raise AssertionError('Invalid or conflicting binding accepted')
    duplicate=copy.deepcopy(changed);duplicate['letter_style']='custom';duplicate['letter_keys']['h']=fn;rejects(duplicate)
    duplicate=copy.deepcopy(changed);duplicate['keypad_keys']['h']=keys.physical_key(ord('S'),0x1f);rejects(duplicate)
    num=copy.deepcopy(changed);num['keypad_keys']['h']=keys.physical_key(0x90,0x45,True);rejects(num)
    num['symbol_toggle']='';keys.validate(num)
    assert keys.physical_vk(0x2e,0x53,False)==0x6e and keys.physical_vk(0x2e,0x53,True)==0x2e
    assert not keys.overlaps(keys.physical_key(0x2e,0x53,True),'KP_Decimal')
    assert keys.overlaps(keys.physical_key(0x2e,0x53,False),'KP_Decimal')
    moved,cleared=keys.assign(settings,'keypad_h',keys.physical_key(ord('S'),0x1f))
    assert cleared==['letter_s'] and moved['letter_keys']['s']==''
    assert moved['letter_style']==moved['keypad_style']=='custom'
    moved,cleared=keys.assign(moved,'letter_p',keys.physical_key(ord('S'),0x1f))
    assert cleared==['keypad_h'] and moved['keypad_keys']['h']==''
    moved,cleared=keys.assign(moved,'keypad_h',keys.physical_key(0x90,0x45,True))
    assert cleared==['symbol_toggle'] and moved['symbol_toggle']==''
    moved,cleared=keys.assign(moved,'symbol_toggle',keys.physical_key(0x90,0x45,True))
    assert cleared==['keypad_h'] and moved['keypad_keys']['h']==''
    assert keys.validate(json.loads(json.dumps(moved)))==moved
    for vk,scan,extended in [(0xa0,0x2a,0),(0xa1,0x36,0),(0xa3,0x1d,1),(0x0d,0x1c,0),(0x0d,0x1c,1),(0x14,0x3a,0),(0x1b,1,0)]:
        sample=copy.deepcopy(changed);sample['keypad_keys']['h']=keys.physical_key(vk,scan,extended);rejects(sample)
    native=None
    if args.native_probe:
        native=json.loads(subprocess.check_output([args.native_probe],encoding='utf-8'));assert native['result']=='PASS' and native['abi_bytes']==28
        for row in native['vectors']:
            try:spec=keys.parse_key(row['token'])
            except ValueError:assert not row['valid'];continue
            assert row['valid'] and row['reserved']==bool(keys.reserved_reason(row['token'])) and row['virtual']==keys.resolved_vk(spec),row
    result={'result':'PASS','cross_group_conflicts':True,'reserved_control_priority':True,'any_raw_event_without_device_whitelist':True,'weak_and_extended_identities':True,'numlock_can_move_or_disable':True,'native_vectors_verified':native is not None,'scope':'Config and native resolver; actual hardware Fn delivery requires TSF host verification.'}
    if args.report:args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
