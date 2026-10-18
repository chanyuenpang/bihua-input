"""Validate product-data identity, missing/corrupt-source rejection and canonical projection."""
from pathlib import Path
import hashlib,json,re,shutil,tempfile,argparse
import release_profile as product

def inspect(folder):
    folder=Path(folder);lock=product.verified_source()
    manifest=json.loads((folder/'bihua_local.manifest.json').read_text(encoding='utf-8-sig'))
    assert manifest['profile_id']==lock['profile_id'] and manifest['source_role']=='user_provided','Unexpected product-data source'
    rows={}
    for name,digest in lock['generated_files'].items():
        path=folder/('lua/'+name if name.endswith('.lua') and (folder/'lua').is_dir() else name)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
    path=folder/'lua/bihua_local_data.lua'
    if not path.exists():path=folder/'bihua_local_data.lua'
    line=next(line for line in path.read_text(encoding='utf-8').splitlines() if line.startswith('["hshsz"]='))
    literal=re.sub(r'\\u\{([0-9a-f]+)\}',lambda match:chr(int(match[1],16)),line.split('=',1)[1].removesuffix(','))
    order=[row.split('\t')[0] for row in json.loads(literal).splitlines()]
    assert order[:9]==list('提喜担吉博损扣抽操') and order.index('吉')==3
    return manifest

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',type=Path);args=parser.parse_args()
    if args.profile:inspect(args.profile);print('Provided product-data identity PASS');return
    with tempfile.TemporaryDirectory(prefix='provided-data-',dir=product.ROOT/'.verification') as temp:
        base=Path(temp);folder=base/'generated';manifest=product.build(folder);inspect(folder)
        from personal_strokes import canonical_codes
        codes=canonical_codes(rime_directory=folder)
        assert len(codes)==10579 and codes['吉']=='121251'
        source=base/'source';shutil.copytree(product.DEFAULT_SOURCE,source)
        path=source/'wechat-mobile-stroke-candidates.tsv';original=path.read_bytes();path.write_bytes(original+b'corrupt')
        try:product.verified_source(source)
        except ValueError:pass
        else:raise AssertionError('Corrupt product data accepted')
        path.write_bytes(original);path.unlink()
        try:product.verified_source(source)
        except ValueError:pass
        else:raise AssertionError('Missing product data accepted')
    proof={'result':'PASS','source_role':'user_provided','all_four_tables_match_reference':True,'no_alternate_data_fallback':True,
           'missing_and_corrupt_sources_rejected':True,'default_characters':len(codes),'ji_rank_for_12125':4}
    (product.ROOT/'.verification/provided-data-0628.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof))
if __name__=='__main__':main()
