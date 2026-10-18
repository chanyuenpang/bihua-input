"""Reproducible redistributable profile from Conway Stroke Data, never phone data."""
import argparse
from collections import defaultdict,Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re

COMMIT='e09e3ce76e9bba7425233091efa2829e89ff3f74'
def literal(value): return json.dumps(value,ensure_ascii=False)

def build(source,output):
    spec=importlib.util.spec_from_file_location('conway',source/'generate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rank={}
    for line in (source/'ranking-simplified.txt').read_text(encoding='utf-8').splitlines():
        if line.startswith('#'): continue
        for char in line.strip(): rank.setdefault(char,len(rank))
    codes={}
    for line in (source/'codepoint-character-sequence.txt').read_text(encoding='utf-8').splitlines():
        match=re.fullmatch(r'U\+([0-9A-F]{4,5})!?\t(\S)[\^*]?\t([1-5|()\\]+)',line)
        if not match: continue
        char=match[2];assert ord(char)==int(match[1],16)
        values=sorted(module.to_sequence_set(match[3]),key=lambda x:(len(x),x))
        assert all(re.fullmatch('[1-5]+',v) for v in values)
        codes[char]=values
    assert len(codes)>28000
    canonical={char:values[0] for char,values in codes.items()}
    ordered=sorted(codes,key=lambda ch:(rank.get(ch,50000),not (0x4e00<=ord(ch)<=0x9fff),ord(ch)))
    prefixes=defaultdict(list)
    for index,char in enumerate(ordered):
        score=max(1,100000-index)
        seen=set()
        for code in codes[char]:
            for length in range(1,len(code)+1):
                prefix=code[:length]
                if prefix in seen: continue
                seen.add(prefix)
                if len(prefixes[prefix])<120: prefixes[prefix].append((char,score,int(prefix in codes[char])))
    words=[]
    for line in (source/'phrases-simplified.txt').read_text(encoding='utf-8').splitlines():
        word=line.strip()
        if 2<=len(word)<=4 and all(ch in codes and len(canonical[ch])<=52 for ch in word): words.append(word)
    words=sorted(set(words),key=lambda word:(sum(rank.get(ch,10000) for ch in word)/len(word),word))
    tails=defaultdict(lambda:defaultdict(list));associations=defaultdict(Counter)
    translate=str.maketrans('12345','hspnz')
    for i,word in enumerate(words):
        weight=max(1,100000-i)
        tails[word[0]][len(word)-1].append((word[1:],weight,'|'.join(canonical[ch].translate(translate) for ch in word[1:])))
        for j in range(1,len(word)):
            for n in range(1,min(j,3)+1): associations[word[j-n:j]][word[j]]+=weight
    output.mkdir(parents=True,exist_ok=True)
    data=['-- Derived from Conway Stroke Data, CC-BY-4.0; see THIRD-PARTY.txt.','local packed=require("bihua_packed_data")','return {codes={']
    data += [f'[{literal(ch)}]={literal(code.translate(translate))},' for ch,code in sorted(canonical.items())]
    data+=['},prefixes=packed.prefixes({']
    data += [f'[{literal(prefix.translate(translate))}]={literal("".join(ch+chr(9)+str(score)+chr(9)+str(exact)+chr(10) for ch,score,exact in rows))},' for prefix,rows in sorted(prefixes.items())]
    data+=['})}']
    (output/'bihua_local_data.lua').write_text('\n'.join(data),encoding='utf-8')
    dictionary=['---','name: bihua_local','version: "0.6.0"','sort: by_weight','use_preset_vocabulary: false','...']
    for i,ch in enumerate(ordered):
        for code in codes[ch]: dictionary.append(f'{ch}\t{code.translate(translate)}\t{max(1,100000-i)}')
    (output/'bihua_local.dict.yaml').write_text('\n'.join(dictionary)+'\n',encoding='utf-8')
    assoc=['return require("bihua_packed_data").associations({']
    for context,rows in sorted(associations.items()):
        packed=''.join(ch+'\t'+str(weight)+'\n' for ch,weight in rows.most_common(120))
        assoc.append(f'[{literal(context)}]={literal(packed)},')
    (output/'bihua_local_associations.lua').write_text('\n'.join(assoc+['})']),encoding='utf-8')
    phrases=['return {codes={']+[f'[{literal(ch)}]={literal(canonical[ch].translate(translate))},' for ch in sorted(tails)]+['},tails=require("bihua_packed_data").tails({']
    for first,groups in sorted(tails.items()):
        phrases.append(f'[{literal(first)}]={{')
        for length,rows in sorted(groups.items()):
            packed=''.join(text+'\t'+str(weight)+'\t'+packed+'\n' for text,weight,packed in rows)
            phrases.append(f'[{length}]={literal(packed)},')
        phrases.append('},')
    (output/'bihua_local_phrase_data.lua').write_text('\n'.join(phrases+['})}']),encoding='utf-8')
    with (output/'canonical_strokes.tsv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,delimiter='\t');writer.writerow(['character','stroke_digits']);writer.writerows(sorted(canonical.items()))
    digest=hashlib.sha256((output/'canonical_strokes.tsv').read_bytes()).hexdigest()
    (output/'canonical_strokes.sha256').write_text(digest,encoding='ascii')
    result={'profile_id':'conway-open-'+COMMIT[:12],'source_role':'redistributable','source_commit':COMMIT,
            'characters':len(codes),'prefixes':len(prefixes),'phrases':len(words),'association_keys':len(associations),
            'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file() and p.stat().st_size},
            'generated_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output/'bihua_local.manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.source,args.output)
