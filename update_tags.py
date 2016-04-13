import os
import sys

import cloud_setup

if len(sys.argv) != 3:
    print "Usage: python update_tags.py key value"
    exit(1)

instance_tag = os.environ.get('TAG')
new_key = sys.argv[1]
new_val = sys.argv[2]

if instance_tag:
  cloud_setup.add_tag(instance_tag, new_key, new_val)
else:
  print "**************************************************"
  print "* ERROR: Unable to find TAG environment variable *"
  print "**************************************************"
