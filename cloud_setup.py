# These are the run-once tasks to get AWS ready-for-use, in addition to
# utilities used by our scripts to access AWS.
import os
import time
import boto.ec2
import boto.exception
import boto.manage.cmdshell
import boto.sdb
import pprint

SSH_FOLDER = os.path.expanduser("~/.ssh/")
AWS_REGION = "us-east-1"  # US East (Virginia)


def create_keypair(key_name):
    """
    Create the public-key crypto pair so we can log in to our new instances.
    AWS stores the public key under a name we provide, we need to save the
    private key ourselves.
    """
    if os.path.isfile(SSH_FOLDER + key_name + ".pem"):
        return  # Key already created
    ec2 = boto.ec2.connect_to_region(AWS_REGION)
    key = ec2.create_key_pair(key_name)
    key.save(SSH_FOLDER)


def create_security_group(group_name):
    """
    Instances are pretty locked down by default. We can assign them to
    security groups to give access rights. This creates a group that mirrors
    the settings recommended by Gurobi.
    """
    ec2 = boto.ec2.connect_to_region(AWS_REGION)
    for g in ec2.get_all_security_groups():
        if g.name == group_name:
            return  # We already have this group setup
    group = ec2.create_security_group(group_name,
                                      "%s SSH access group" % group_name)
    group.authorize("tcp", 22, 22, "0.0.0.0/0")  # SSH is on port 22, all IPs
    group.authorize("tcp", 80, 80, "0.0.0.0/0")
    group.authorize("tcp", 61000, 65000, "0.0.0.0/0")
    print "Created new security group"


def launch_instance(tag, key_name, group_name, inst_type, ami_name, user_data,
                    wait=True, returninfo=None):
    """
    Launch a testing instance. Doesn't actually attempt to connect as
    it can take quite a while between 'running' and connectability
    """
    ec2 = boto.ec2.connect_to_region(AWS_REGION)
    failures = 0
    max_failures = 10
    while True:
        try:
            reservation = ec2.run_instances(ami_name,
                                            key_name=key_name,
                                            security_groups=[group_name],
                                            instance_type=inst_type,
                                            user_data=None)
            break
        except Exception, err:
            # Failed to get instance; wait 15 seconds and then try again (up to
            # 10 total times)
            errortext = str(err)
            if errortext.find("Not authorized for images") >= 0:
                print "**************************************"
                print "* Error from AWS suggests that the AMI code in"
                print "* CloudSetup.py is deprecated. Please go to"
                print "* https://aws.amazon.com/marketplace/ and search for"
                print "* \"Ubuntu server lts hvm\", selecting the most recent"
                print "* version. Click \"Continue\", \"Manual Launch\","
                print "* and then copy the AMI ID for the US East region."
                print "* Copy that to the AMI_NAME value in CloudSetup.py"
                print "* and re-run."
                print "***************************************"
                print "* (Full text of error):"
                print errortext
                print "***************************************"
                return None
            elif errortext.find("accept terms and subscribe") >= 0:
                print "**************************************"
                print "* Error from AWS suggests that you have never used this"
                print "* AMI before and need to accept its terms and"
                print "* subscribe to it. Please follow the link in the below"
                print "* error text. Click \"Continue\", \"Manual Launch\","
                print "* and \"Accept Terms\". After receiving email"
                print "* confirmation, you can re-run the code."
                print "**************************************"
                print "* (Full text of error):"
                print errortext
                print "**************************************"
                return None
            failures += 1
            if failures == max_failures:
                print "**************************************"
                print "* Maximum number of instance launch failures reached."
                print "* (Full text of error):"
                print errortext
                print "**************************************"
                return None
            print "    ** ec2.run_instances failed for tag", tag, "; waiting 15"
            print "    ** seconds and then trying again..."
            time.sleep(15)

    time.sleep(5)  # Slow things down -- they're never running super fast anyway
    instance = reservation.instances[0]
    time.sleep(5)  # Slow things down -- they're never running super fast anyway
    instance.add_tag("tag", tag)
    time.sleep(5)  # Slow things down -- they're never running super fast anyway

    if wait:
        print "    Instance requested, waiting for 'running' for tag", tag
        while instance.state != "running":
            print "    %s ..." % tag
            time.sleep(5)
            try:
                instance.update()
            except boto.exception.EC2ResponseError as e:
                print "******************"
                print "Error caught in instance.update():"
                print e.strerror
                print "******************"
        print "    %s done!" % tag
    if returninfo:
        returninfo.put(tag)
    return instance


def get_instance(tag):
    """
    Get instance by tag
    """
    ec2 = boto.ec2.connect_to_region(AWS_REGION)
    reservations = ec2.get_all_instances()
    for res in reservations:
        for inst in res.instances:
            if "tag" in inst.tags.keys():
                if inst.tags["tag"] == tag and inst.state == "running":
                    #print "Found %s"%tag
                    return inst
    print "Couldn't find instance"
    return None


def connect_instance(tag, key_name, user_name):
    """
    Connect to a running instance using a tag
    """
    inst = get_instance(tag)
    cmd = boto.manage.cmdshell.sshclient_from_instance(
        inst,
        SSH_FOLDER + key_name + ".pem",
        user_name=user_name
    )
    return inst, cmd


def terminate_instance(tag):
    inst = get_instance(tag)
    inst.terminate()


def add_tag(instance_tag, new_tag_key, new_tag_val):
    inst = get_instance(instance_tag)
    inst.add_tag(new_tag_key, new_tag_val)

###############################################################################


def setup_sdb_domain(domain_name):
    sdb = boto.sdb.connect_to_region(AWS_REGION)
    # Only create if it doesn't exist already
    try:
        dom = sdb.get_domain(domain_name, validate=True)
    except:
        # Doesn't exist yet
        dom = sdb.create_domain(domain_name)
    return sdb, dom


def delete_sdb_domain(domain_name):
    sdb, dom = setup_sdb_domain(domain_name)
    sdb.delete_domain(domain_name)


def dump_sdb_domain(domain_name):
    pp = pprint.PrettyPrinter(indent=2)
    sdb, dom = setup_sdb_domain(domain_name)
    rs = dom.select('select * from `' + domain_name + '`')
    for j in rs:
        pp.pprint(j)


def get_sdb_domain_size(domain_name):
    sdb, dom = setup_sdb_domain(domain_name)
    rs = dom.select('select count(*) from `' + domain_name + '`')
    ct = 0
    for res in rs:
        ct += int(res[u'Count'])
    print "Size of", domain_name, ":", ct

###############################################################################


def setup_s3_bucket(bucket_name):
    s3 = boto.s3.connect_to_region(AWS_REGION)
    # Only create if it doesn't exist already
    try:
        bucket = s3.get_bucket(bucket_name, validate=True)
    except:
        # Doesn't exist yet
        bucket = s3.create_bucket(bucket_name)
    return s3, bucket


def delete_s3_bucket(bucket_name):
    s3, bucket = setup_s3_bucket(bucket_name)
    # TODO this needs to empty the bucket first
    s3.delete_bucket(bucket_name)


def add_file_to_s3_bucket(bucket, filekey, filename):
    key = boto.s3.key.Key(bucket)
    key.key = filename + "-" + filekey
    key.set_contents_from_filename(filename)


def download_s3_bucket(bucket_name, output_folder):
    s3, bucket = setup_s3_bucket(bucket_name)

    if not os.path.exists(output_folder):
        os.mkdir(output_folder)

    bucket_list = bucket.list()
    for key in bucket_list:
      d = os.path.join(output_folder, key.key)
      key.get_contents_to_filename(d)


###############################################################################


# Several cleanup tasks to make starting a cluster less annoying:
def clean_known_hosts():
    with open(SSH_FOLDER + "known_hosts", "rU") as fp:
        lines = fp.readlines()
        filtered = [x for x in lines if x.find("ec2-") != 0]
    with open(SSH_FOLDER + "known_hosts", "w") as fp:
        for line in filtered:
            fp.write(line)
    print "Removed", len(lines) - len(filtered), "lines from ~/.ssh/known_hosts"


def get_num_running():
    ec2 = boto.ec2.connect_to_region(AWS_REGION)
    reservations = ec2.get_all_instances()
    num_shutting_down = 0
    num_pending_running = 0
    num_stop = 0
    num_terminate = 0
    for res in reservations:
        for inst in res.instances:
            if inst.state == "shutting-down":
                num_shutting_down += 1
            elif inst.state in ["pending", "running"]:
                num_pending_running += 1
            elif inst.state in ["stopping", "stopped"]:
                num_stop += 1
            elif inst.state == "terminated":
                num_terminate += 1
    return (num_shutting_down, num_pending_running, num_stop, num_terminate)


def print_num_running():
    nr = get_num_running()
    print "Number Shutting Down:", nr[0]
    print "Number Pending or Running:", nr[1]
    print "Number Stopping or Stopped:", nr[2]
    print "Number Terminated:", nr[3]


# Wait for all the EC2 nodes that are in shutting-down to go to status
def wait_for_shutdown():
    while True:
        n_shut_down, n_pend_run, n_stop, n_terminate = get_num_running()
        if n_shut_down == 0:
            print "No nodes shutting down"
            return
        else:
            print (n_shut_down, "instance(s) still shutting down and",
                   n_pend_run, "pending/running; waiting")
            time.sleep(5.0)
