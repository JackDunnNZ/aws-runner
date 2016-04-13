import json
import os
import urllib

AMI_URL = "http://packages.gurobi.com/ami.json"
CLOUDKEY_FILE_PATH = "config/GUROBI_CLOUD_KEY.txt"
DEFAULT_USER = "ubuntu"


class AMIResolver(object):
    def __init__(self):
        self.ami_list = None

    def get_ami_list(self):
        if not self.ami_list:
            print "Updating AMI list..."
            response = urllib.urlopen(AMI_URL)
            self.ami_list = json.loads(response.read())
        return self.ami_list

    def get_ami_name(self, aws_region):
        return self.get_ami_list().get(aws_region, None)


def generate_user_data(cloudkey, password, idleshutdown=30):
    return ("CLOUDKEY=%s\n"
            "PASSWORD=%s\n"
            "ADMINPASSWORD=%s\n"
            "IDLESHUTDOWN=%d") % (cloudkey, password, password, idleshutdown)


def get_cloudkey():
    # Locate the GUROBI_CLOUD_KEY file
    if not os.path.exists(CLOUDKEY_FILE_PATH):
        print "************************************************************"
        print "* ERROR: Could not locate Gurobi Cloud license key at"
        print "*     '%s'" % os.path.join(os.getcwd(), CLOUDKEY_FILE_PATH)
        print "************************************************************"
        exit(1)
    with open(CLOUDKEY_FILE_PATH, "r") as f:
        cloudkey = f.read().strip()
    if not cloudkey:
        print "************************************************************"
        print "* ERROR: Found but could not read Gurobi Cloud license key at"
        print "*     '%s'" % os.path.join(os.getcwd(), CLOUDKEY_FILE_PATH)
        print "************************************************************"
        exit(1)
    return cloudkey
