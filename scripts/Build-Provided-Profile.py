"""Generate the pinned product tables from the source snapshot in this repository."""
from pathlib import Path
import argparse
import json
import release_profile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=release_profile.ROOT/'.verification/provided-profile')
args=parser.parse_args()
manifest=release_profile.build(args.output)
print(json.dumps({'profile':manifest['profile_id'],'directory':str(args.output),'core_tables':len(manifest['generated_files'])}))
