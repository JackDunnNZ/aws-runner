import argparse
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


def setup_instances(tags, cmds, insts, install_file, localpaths, remotepaths,
                    verbose=True):
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
        f.put(install_file, "INSTALL.sh")
        # Python script to run INSTALL.sh
        f.put("INSTALL.py", "INSTALL.py")
        # For updating tags and results
        f.put("update_tags.py", "update_tags.py")
        f.put("save_results.py", "save_results.py")
        f.put("cloud_setup.py", "cloud_setup.py")
        f.put(botoloc, ".boto")
        # Put the specified code folder
        for localpath, remotepath in zip(localpaths, remotepaths):
            put_all(f, localpath, remotepath)

        f.close()

        # Setting CLOUDKEY by user data doesn't seem to work
        # Set it by curl instead
        inst_id = insts[tag].id
        cloudkey = gurobi_aws.get_cloudkey()
        cmds[tag].run(
            "curl --data \"type=CLOUDKEY&adminpassword=%s&data=%s\" "
            "http://localhost/update_settings" % (inst_id, cloudkey))

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

    localpath = os.path.abspath(localpath)
    print "    Copying code folder to machine:"
    print "        " + localpath

    # First make the containing folder on the remote
    print "    Making remote folder: %s" % remotepath
    mkdir_p(f, remotepath)

    os.chdir(os.path.split(localpath)[0])
    parent = os.path.split(localpath)[1]
    for walker in os.walk(parent):
        remotename = walker[0][len(parent) + 1:]
        # Skip git objects folder for speed
        if remotename[:12] == ".git/objects":
            continue
        print "        Copying " + walker[0]
        try:
            f.mkdir(os.path.join(remotepath, remotename))
        except:
            pass
        for file in walker[2]:
            print "            " + os.path.join(walker[0], file),
            print "> " + os.path.join(remotepath, remotename, file)
            f.put(os.path.join(walker[0], file),
                  os.path.join(remotepath, remotename, file))

    os.chdir(cwd)


def mkdir_p(sftp, remote, is_dir=True):
    """
    emulates mkdir_p if required.
    sftp - is a valid sftp object
    remote - remote path to create.
    """
    dirs_ = []
    if is_dir:
        dir_ = remote
    else:
        dir_, basename = os.path.split(remote)
    while len(dir_) > 1:
        dirs_.append(dir_)
        dir_, _  = os.path.split(dir_)

    if len(dir_) == 1 and not dir_.startswith("/"):
        dirs_.append(dir_) # For a remote path like y/x.txt

    while len(dirs_):
        dir_ = dirs_.pop()
        try:
            sftp.stat(dir_)
        except:
            print "making ... dir",  dir_
            sftp.mkdir(dir_)


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
            f.write("cd code")
            f.write("\n")
            f.write(command)
            f.write("\n")
            f.write("python ~/save_results.py %s %s %s" %
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
            "nohup bash runner.sh &> screen_output.txt &"
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


def run_dispatch(job, commands, instance_types, install_file, codepath,
                 extra_code_paths, results_file, create, dispatch, verbose):
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
    if (not os.path.exists("INSTALL.py")):
        print "Please run this script from the aws-runner directory."
        exit(1)
    if (not os.path.exists(install_file)):
        print "Could not find the install file:"
        print "    %s" % install_file
        exit(1)
    if (not os.path.exists(codepath)):
        print "Could not find the code folder:"
        print "    %s" % codepath
        exit(1)

    # Load and validate extra code paths
    localpaths = [codepath]
    remotepaths = ["code"]
    for extra_code_path in extra_code_paths:
        split_path = extra_code_path.split("=")
        if len(split_path) != 2:
            print "The following extra code path was malformed. It needs to",
            print "be in the form /local/path=/remotepath"
            print "    %s" % extra_code_path
            exit(1)
        localpath = split_path[0]
        remotepath = split_path[1]
        if not os.path.exists(localpath):
            print "Could not find the local part of the extra code path:"
            print "    %s" % localpath
            print "The extra code path was:"
            print "    %s" % extra_code_path
            exit(1)
        localpaths.append(localpath)
        remotepaths.append(remotepath)

    if verbose:
        print "Code folders to copy (local => remote):"
        for localpath, remotepath in zip(localpaths, remotepaths):
            print "    %s => %s" % (localpath, remotepath)

    tags = ["%s%d" % (job, i) for i in range(len(commands))]

    print "Overview for job %s" % job
    for tag, inst_type, command in zip(tags, instance_types, commands):
        print "   %s%s%s" % (tag.ljust(20), inst_type.ljust(20), command)

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

    print "Using Gurobi AMI:"
    print "    %s" % ami_name

    cloudkey = gurobi_aws.get_cloudkey()
    user_data = gurobi_aws.generate_user_data(cloudkey, job)

    print "Using user_data:"
    print user_data

    # Setup security group and key pair (these are no-ops if done before)
    cloud_setup.create_security_group(job)
    cloud_setup.create_keypair(job)

    # Do some work upfront (clean out ~/.ssh/known_hosts and wait until all
    # shutting down nodes are shut down).
    cloud_setup.clean_known_hosts()
    cloud_setup.wait_for_shutdown()

    # Create instances if desired
    # if create:
    #     create_instances(job, tags, ami_name, user_data, instance_types,
    #                      verbose)

    # Connect to all the instances
    if create or dispatch:
        insts, cmds = connect_instances(job, tags, verbose)

    # Set them up (if desired)
    if create:
        setup_instances(tags, cmds, insts, install_file, localpaths,
                        remotepaths, verbose)

    # Send out jobs and start machines working (if desired)
    if dispatch:
        dispatch_and_run(job, tags, cmds, commands, results_file, verbose)

    print ""
    print "All dispatcher tasks successfully completed."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A helper script to dispatch computation to AWS. "
                    "Please see the README for usage instructions."
    )
    parser.add_argument("jobname", type=str,
                        help="A descriptive name for this job.")
    parser.add_argument("jobfile", type=str,
                        help="Path to the CSV file containing job info.")
    parser.add_argument("install_script", type=str,
                        help="Path to the INSTALL.sh file for setting up "
                             "machines.")
    parser.add_argument("code_folder", type=str,
                        help="Path to the folder containing main code to run.")
    parser.add_argument("results_file", type=str,
                        help="Path to the results CSV file created by the job. "
                             "This path should be relative to `code_folder`.")
    parser.add_argument("-c", "--create", action="store_true",
                        help="Whether to create AWS instances for the jobs.")
    parser.add_argument("-d", "--dispatch", action="store_true",
                        help="Whether to dispatch the jobs to AWS instances.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Output extra progress messages (recommended).")
    parser.add_argument("-e", "--extra_code_path", action="append", type=str,
                        help="Additional folders to copy to the machine. You "
                             "must specify the local path to the folder and "
                             "the path to place it on the remote machine as "
                             "`--extra_code_path /local/path=/remote/path`")
    args = parser.parse_args()

    jobname = args.jobname
    jobfile = args.jobfile
    install_file = args.install_script
    codepath = args.code_folder
    results_file = args.results_file
    create = args.create
    dispatch = args.dispatch
    verbose = args.verbose
    extra_code_paths = args.extra_code_path

    commands, instance_types = extract_job_details(jobfile)

    run_dispatch(jobname, commands, instance_types, install_file,
                 codepath, extra_code_paths, results_file, create, dispatch,
                 verbose)
