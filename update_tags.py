import sys

import cloud_setup

if len(sys.argv) != 4:
    print "Usage: python update_tags.py instance_tag new_key new_val"
    exit(1)

instance_tag = sys.argv[1]
new_key = sys.argv[2]
new_val = sys.argv[3]

cloud_setup.add_tag(instance_tag, new_key, new_val)
