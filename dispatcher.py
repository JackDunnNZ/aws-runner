import csv
import multiprocessing
import os
import sys
import time

import cloud_setup
import gurobi_aws


def create_instances(job, tags, ami_name, user_data, instance_types,
                     verbose=True):
    """
    Simply create an instance for each tag. Uses multiprocessing to create them
    in parallel.
    """

    if verbose:
        print "Launching instances... "
    procs = []
    returninfo = multiprocessing.Queue()
    for tag, instance_type in zip(tags, instance_types):
        if verbose:
            print "  Launching %s ..." % tag

        proc = multiprocessing.Process(
            target=cloud_setup.launch_instance,
            args=(),
            kwargs={
                "tag": tag,
                "key_name": job,
                "group_name": job,
                "inst_type": instance_type,
                "ami_name": ami_name,
                "user_data": user_data,
                "wait": True,
                "returninfo": returninfo,
            }
        )
        procs.append(proc)
        proc.start()

    # Wait for all instances to be launched
    for proc in procs:
        proc.join()

    # Count number of processes that have launched
    numstarted = 0
    try:
        while True:
            returninfo.get(False)
            numstarted += 1
    except:
        pass  # Queue is empty

    # Check we all started correctly
    if numstarted != len(tags):
        print "Exiting because", numstarted, "instances started out of",
        print len(tags)
        exit(0)

    if verbose:
        print " All instances launched, but not necessarily ready for"
        print " SSH though - check AWS console to get a better idea."
        print " Hit [RETURN] to proceed to connection attempt."
        raw_input()


def connect_instances(job, tags, verbose=True):
    """
    Connect to the instances. Returns, for every tag, an instance handle and
    a cmdshell handle through which we can execute commands and send and
    receive files.
    Returns:
      insts        Dictionary of tag -> instance
      cmds         Dictionary of tag -> cmdshell
    """

    insts = {}
    cmds = {}
    for tag in tags:
        cmds[tag] = None
    all_done = False
    while not all_done:
        print "Beginning round of connection attempts..."
        all_done = True
        for tag in tags:
            if cmds[tag] is None:
                if verbose:
                    print "  %s" % tag
                # Test if connected
                try:
                    insts[tag], cmds[tag] = cloud_setup.connect_instance(
                        tag=tag,
                        key_name=job,
                        user_name=gurobi_aws.DEFAULT_USER,
                    )
                    cmds[tag].run("ls")
                except:
                    all_done = False
                    cmds[tag] = None

    if verbose:
        print " All connections established, hit [RETURN]"
        raw_input()
    return insts, cmds


def setup_instances(tags, cmds, codepath, verbose=True):
    """
    Install dependencies and build so it is ready for the run. This takes
    a while so after copying the files we just fire off a script.
    multiprocessing didn't work nicely with this...
    """

    # Locate the .boto file
    if os.path.exists(".boto"):
        botoloc = ".boto"
    elif os.path.exists(os.path.expanduser("~/.boto")):
        botoloc = os.path.expanduser("~/.boto")
    else:
        print "Could not locate .boto file"
        exit(1)

    if verbose:
        print "Copying keys, etc. to all instances, running INSTALL... "

    for tag in tags:
        print "    Copying files to %s ..." % (tag)
        f = cmds[tag].open_sftp()

        # The install script
        f.put("INSTALL.sh", "INSTALL.sh")
        # Python script to run INSTALL.sh
        f.put("INSTALL.py", "INSTALL.py")
        # For updating tags and results
        f.put("update_tags.py", "update_tags.py")
        f.put("save_results.py", "save_results.py")
        f.put("cloud_setup.py", "cloud_setup.py")
        f.put(botoloc, ".boto")
        # Put the specified code folder
        put_all(f, codepath, "code")

        f.close()

        # Make script executable
        cmds[tag].run("chmod +x INSTALL.sh")

        # Spawn the install runner (non-blocking)
        print "    Launching INSTALL.py on %s ..." % (tag)
        stdin, stdout, stderr = cmds[tag]._ssh_client.exec_command(
            "python INSTALL.py")

    print "    Waiting for INSTALL.py to complete on all machines"
    while True:
        time.sleep(10)
        done = [cmds[tag].run("ls .")[1].find("READY") >= 0 for tag in tags]
        print "      - Installation complete on",
        print sum(done), "/", len(done), "boxes"
        if sum(done) == len(done):
            break

    if verbose:
        print " Hit [RETURN] when ready to proceed."
        raw_input()


def put_all(f, localpath, remotepath):
    """
    Recursively uploads a full directory over an SFTP session.
    """
    cwd = os.getcwd()

    os.chdir(os.path.split(localpath)[0])
    parent = os.path.split(localpath)[1]
    for walker in os.walk(parent):
        try:
            f.mkdir(os.path.join(remotepath, walker[0]))
        except:
            pass
        for file in walker[2]:
            f.put(os.path.join(walker[0], file),
                  os.path.join(remotepath, walker[0], file))

    os.chdir(cwd)


def dispatch_and_run(job, tags, cmds, commands, results_file, verbose=True):
    """
    Spawn the relevant command on each instance
    """
    # Write out and copy to instances
    if verbose:
        print "Writing args file and starting run... "

    for tag, command in zip(tags, commands):
        if verbose:
            print " %s" % tag

        # Make a shell script to run the command and then save the results
        runner_path = "runner_%s.sh" % tag
        with open(runner_path, "w") as f:
            f.write("export TAG=%s" % tag)  # Inject tag as environment var
            f.write("\n")
            f.write(command)
            f.write("\n")
            f.write("python save_results.py %s %s %s" %
                    (job, tag, results_file))

        # Put runner to server
        f = cmds[tag].open_sftp()
        f.put(runner_path, "runner.sh")
        f.close()

        # Cleanup
        try:
            os.remove(runner_path)
        except:
            pass

        cmds[tag].run("chmod +x runner.sh")

        cmds[tag]._ssh_client.exec_command(
            "cd code; nohup bash runner.sh &> screen_output.txt &"
        )

    if verbose:
        print "\n  Computation started on all machines"


def extract_job_details(jobfile):
    commands = []
    instance_types = []
    with open(jobfile, "rU") as f:
        reader = csv.reader(f)
        header_line = reader.next()
        if header_line[0] != "instance_type" or header_line[1] != "command":
            print "Error reading specified jobfile: %s" % jobfile
            print ""
            print "Make sure the jobfile is a csv file with instance types "
            print "in the first column and commands in the second."
            print "The headers should be 'instance_type' and 'command'."
            exit(1)

        for line in reader:
            if len(line) > 2:
                print "Error reading specified jobfile: %s" % jobfile
                print ""
                print "Make sure the jobfile is a csv file with instance types "
                print "in the first column and commands in the second."
                print "A row had more than two columns."
                exit(1)
            instance_types.append(line[0])
            commands.append(line[1])
    return commands, instance_types


def run_dispatch(job, commands, instance_types, codepath, results_file, create,
                 dispatch, verbose):
    """
    Setup machines, run jobs, monitor, then tear them down again.
    """

    if (not len(commands) == len(instance_types)):
        print "Different number of commands and instance types"
        exit(1)

    # Validate that required files exist
    if (not os.path.exists(".boto") and
            not os.path.exists(os.path.expanduser("~/.boto"))):
        print "Please create a .boto file containing your AWS credentials as",
        print "described in README.md. Store this file either in the "
        print "aws-runner folder or in your home directory."
        exit(1)
    if (not os.path.exists(gurobi_aws.CLOUDKEY_FILE_PATH)):
        print "Please create a GUROBI_CLOUD_KEY file containing your AWS",
        print "Gurobi prepaid license in the config folder."
        exit(1)
    if (not os.path.exists("INSTALL.sh") or
            not os.path.exists("INSTALL.py")):
        print "Please run this script from the aws-runner directory."
        exit(1)

    tags = ["%s%d" % (job, i) for i in range(len(commands))]

    # Get the Gurobi AMI for the selected AWS region
    resolver = gurobi_aws.AMIResolver()
    ami_name = resolver.get_ami_name(cloud_setup.AWS_REGION)
    if not ami_name:
        print "There was no Gurobi AMI found for the specified AWS region."
        print "The specified AWS region was:"
        print "    %s" % cloud_setup.AWS_REGION
        print "All available Gurobi AMIs:"
        for (region, ami) in resolver.get_ami_list().iteritems():
            print "    %s%s" % (region.ljust(20), ami)

    cloudkey = gurobi_aws.get_cloudkey()
    user_data = gurobi_aws.generate_user_data(cloudkey, job)

    # Setup security group and key pair (these are no-ops if done before)
    cloud_setup.create_security_group(job)
    cloud_setup.create_keypair(job)

    # Do some work upfront (clean out ~/.ssh/known_hosts and wait until all
    # shutting down nodes are shut down).
    cloud_setup.clean_known_hosts()
    cloud_setup.wait_for_shutdown()

    # Create instances if desired
    if create:
        create_instances(job, tags, ami_name, user_data, instance_types,
                         verbose)

    # Connect to all the instances
    if create or dispatch:
        insts, cmds = connect_instances(job, tags, verbose)

    # Set them up (if desired)
    if create:
        setup_instances(tags, cmds, codepath, verbose)

    # Send out jobs and start machines working (if desired)
    if dispatch:
        dispatch_and_run(job, tags, cmds, commands, results_file, verbose)

    print ""
    print "All dispatcher tasks successfully completed."

if __name__ == "__main__":
    create = not ("nocreate" in sys.argv)
    dispatch = not ("nodispatch" in sys.argv)
    verbose = "verbose" in sys.argv

    if len(sys.argv) != 5:
        print "Usage: python dispatcher.py jobname jobfile /path/to/code ",
        print "path/to/results/file [nocreate] [nodispatch] [verbose]"
        exit(1)

    jobname = sys.argv[1]
    jobfile = sys.argv[2]
    codepath = sys.argv[3]
    results_file = sys.argv[4]

    commands, instance_types = extract_job_details(jobfile)

    run_dispatch(jobname, commands, instance_types, codepath, results_file,
                 create, dispatch, verbose)
