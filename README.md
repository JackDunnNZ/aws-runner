# Computation with Amazon Web Services

This is a collection of scripts to help you easily perform distributed computation using Gurobi on Amazon Web Services (AWS). These were adapted from code originally by [Iain Dunning](https://github.com/IainNZ).

## Setting up required software

To get starting, you need to install several pieces of software on your system to interface with AWS:

 * Python version 2.7 should be installed
 * If you do not already have the Python package manager `pip` installed, install it by following the instructions [on the pip website](https://pip.pypa.io/en/latest/installing.html).
 * Install required python packages with `sudo pip install paramiko` and `sudo pip install boto`. The `paramiko` package dependencies `ecdsa` and `pycrypto` should be automatically installed; if they are not follow the additional [paramiko installation instructions](http://www.paramiko.org/installing.html).

## Configuring an Amazon Web Services account

The first step is to set up an Amazon Web Services account:

 * Register for an account at [aws.amazon.com](https://aws.amazon.com) (registration will require credit card information).
 * Log in to the AWS console at [console.aws.amazon.com](https://console.aws.amazon.com).
 * Navigate to "Identity & Access Management"; click "Users" and "Create New Users", creating one new user with "Generate an access key for each user" checked.
 * Click "Show User Security Credentials", which should show a "Access Key ID" value and a "Secret Access Key" value. Use these values to create a file located at `~/.boto` with the following format (filling in the *'s with the value from the user security credentials).
```
[Credentials]
aws_access_key_id = **************
aws_secret_access_key = **************
```
 * From the console, navigate to "Identity & Access Management"; click "Users" and select the new user. Under "Inline Policies", click the text "click here" to add a new inline policy (you may need to click the arrow in the "Inline Policies" heading to display this text). Click "Custom Policy" and "Select", entering any policy name desired and the following policy (which grants the user full access to the account):
```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*"
    }
  ]
}
```

## Getting a Gurobi Cloud license for AWS

You will need a Gurobi Cloud license key in order to run Gurobi on AWS. You can obtain a prepaid license for a specified number of hours by contacting Gurobi licensing (this is free for academic use).

Once you have this license, you should create a file in the `config` folder called `GUROBI_LICENSE_KEY.txt` containing the license key. Alternatively, you can rename the example file in this folder and paste in the license key. Do **NOT** commit this file or share it e.g. to Github, as it will let anyone use your Gurobi license! 

## Getting your code ready for AWS

The following is an overview of how the computation will be carried out when using this package::

- The work you want to do can be broken into smaller, parallelizable jobs.
- An AWS machine will be created for each job, and will carry out the computation for this job independently of all other jobs.
- Each job will be started by a single command-line string.
- Each job produces one or more output files that describe all the information you require.

You need to decide how to break up your computation into jobs, and make sure that each job can be run from a single command-line string. Packages like [ArgParse.jl](https://github.com/carlobaldassi/ArgParse.jl) can be helpful in writing a command-line wrapper for your code.

For example, if you have some Julia code to run an experiment, and you want to run it with different starting seeds on each machine, you might create a wrapper that can be called as:

```
julia wrapper.jl --seed <seed>
```

for different values of `<seed>`.

You must also modify your code to save all relevant results from the individual job into a single CSV file. When the job is finished, the machine is terminated and all that remains are the contents of this CSV file, so make sure it contains all output that you require.

You also need to decide which type of AWS EC2 instance you are going to use for each job. You should consult a description of [instance types](https://aws.amazon.com/ec2/instance-types/) and their [pricing](https://aws.amazon.com/ec2/pricing/). The main factors driving price are the memory size and CPU power, so you should choose machines that closely match your hardware requirements (try running your code locally to get an estimate for memory usage). By default, the computation will be carried out in the `us-east-1` region, although this can be modified by changing `AWS_REGION` in `cloud_setup.py`.

By default an account is limited to 20 simultaneous EC2 nodes of a given type, though an increase can be requested on the AWS Console by selecting the region e.g. "US East", selecting EC2, and then selecting "Limits" on the navigation pane on the left, requesting a limit increase for the instance type.

## Configuring your job details

Once your code has been prepared, you have decided on how to break up your workload into jobs, and you know which instance type to use for each job, you can prepare the `jobdetails.csv` file. This file is a two-column CSV file, where the first line must contain the headers `instance_type` and `command`. Each subsequent line contains the details for a single job. The value in the first column is the instance type you require for this job, and the value in the second column is the corresponding command-line string to run.

For example, if the workload uses the `wrapper.jl` script described earlier, and wants to run this for five different seeds, using `t2.small` instances, the `jobdetails.csv` should be:

```
instance_type,command
t2.small,julia wrapper.jl --seed 1
t2.small,julia wrapper.jl --seed 2
t2.small,julia wrapper.jl --seed 3
t2.small,julia wrapper.jl --seed 4
t2.small,julia wrapper.jl --seed 5
```

This file is included as an example in the `config` directory.

## Configuring AWS setup script

When the AWS instance starts, it will be a fresh installation of Ubuntu with no additional software other than Gurobi. You will need to install any additional software that your code requires, for example Julia or R.

A shell script is run after is run after creating the machine to do this installation. The example `INSTALL.sh` file installs Julia and R, as well as some packages for these languages. You can modify this file to match the installation you require or create your own script. It must create a file `READY` in the home directory when it has successfully executed..

## Launching Computation on EC2

The file `dispatcher.py` is used to start the computation job. This script should be run with the following arguments:

```
$ python dispatcher.py -h
usage: dispatcher.py [-h] [-c] [-d] [-v] [-i EXTRA_INPUT_CODE_PATH]
                     [-o EXTRA_OUTPUT_FILE] [--tag_offset TAG_OFFSET]
                     jobname jobfile install_script code_folder results_file
```

Arguments:

1. `jobname` is the name given to this job for identification purposes.
2. `jobfile` should be the path to the `jobdetails.csv` file you created earlier with the instance types and commands for each job.
3. `install_script` is the path to the `INSTALL.sh` script.
4. `code_folder` should be the path of the folder that contains all of the code needed for running your jobs. This folder will be copied to each instance during the setup process.
5. `results_file` should be the path to the CSV file that will be created after your job has run. This path must be **relative** to the code folder. For example, if your code is in `/code/`, and your script outputs its results file to `/code/results/results.csv`, you should specify `results/results.csv` as the results file.
6. `-c, --create` is an optional argument which will create the machines and run the installation script. It should only be omitted if the machines are already created and set up.
7. `-d, --dispatch` is an optional argument which will start the computation on the machines once they are setup..
8. `-v, --verbose` is an optional argument which will make the script display information as it runs.
9. `-i, --extra_input_code_path` allows you to specify additional folders to copy to the machines. You must specify the local path to the folder and the path to place it on the remote machine as `--extra_input_code_path /local/path=/remote/path`
10. `-o, --extra_output_file` allows you to specify additional results files to upload to S3. These paths should again be relative to `code_folder`.
11. `--tag_offset` allows you to specify the starting point for numbering machines. The script uses these numbers to refer to the machines uniquely, and defaults to starting at zero. If you already have machines running, you should set this to a number that is greater than the tag number of all currently running machines.

For the example computation described earlier, a call to `dispatcher.py` might look like

```
python dispatcher.py myexamplejob config/jobdetails.csv /code/ results/results.csv --create --dispatch --verbose
```

This will produce output as the dispatcher launches new instances, connects to the instances, sets up the instances for the run, distributes the work for the run, and starts the run on each node. Once the launch script exits, all nodes will be running, and they will terminate automatically once they have completed all their assigned work. See the "Monitoring Cloud Runs" section below for details on how to monitor a run that is in progress.

## Downloading results

Once the run is completed, the output files are saved in S3 on Amazon Web Services (which has the job name as the S3 bucket name). To download these results to `results.csv` you can run the following:

```
python get_s3_files.py jobname output_folder
```

where `jobname` is the job name that you specified earlier and `output_folder` is the place to put the files.

## Monitoring and Debugging Cloud Runs

There are two major places where a cloud run can fail: during node setup and during the runs themselves.

### Debugging Node Setup Failures

The first time you launch a run on the cloud, it should fail with a message saying that you need to accept the terms and conditions of the Amazon Machine Image (AMI) that we use on EC2. In this case, simply follow the outputted instructions and re-run.

Otherwise, the most likely error to be encountered is one in which the `dispatcher.py` script outputs the following ad infinitum (where `xx` is the number of machines being run on; there is probably trouble if this message appears at least 100 times):

```
      - Installation complete on 0 / xx boxes
      - Installation complete on 0 / xx boxes
      - Installation complete on 0 / xx boxes
      - Installation complete on 0 / xx boxes
      - Installation complete on 0 / xx boxes
      ...
```

This likely indicates an issue in [INSTALL.sh](INSTALL.sh), the script that performs the main setup tasks on each EC2 instance. To resolve such an issue, debug by logging onto a node and looking at the log output generated by [INSTALL.sh](INSTALL.sh). The first step to log into a node is to identify that node's web address. You can do this by logging into the AWS console, selecting "EC2", selecting "Running Instances", selecting an instance, and reading the value under "Public DNS" (we will call this `DNS` in the command that follows). Then you can log into the instance on the command line with:

```
ssh -i ~/.ssh/<jobname>.pem ubuntu@DNS
```

where `jobname` is the job name you specified earlier. Here, `~/.ssh/<jobname>.pem` is a key that was generated when running `dispatcher.py`. It is created by the `cloud_setup.create_keypair` function to enable access to the EC2 nodes without a password.

Once you have logged onto a node, there will be files containing output from the setup tasks with the following names:

* `progress_A_x_x.txt`: Output from configuring `apt` repositories
* `progress_B_x_x.txt`: Output from adding packages with `apt-get`
* `progress_C_x_x.txt`: Output from installing language-specific packages.
* `progress_D_x_x.txt`: Output from building Gurobi.jl at the final step.

If these steps failed to produce a file named `GUROBI_VERSION`, then there may be additional files with output from additional setup attempts (numbered 2, 3, ...). From reading this output, you may be able to identify and correct a setup issue. Once you determine the cause of the error, you can terminate all running instances from the AWS console by navigating to "EC2" and "Running Instances", selecting all the instances, right clicking, and selecting "Instance State -> Terminate".

### Monitoring and Debugging After Setup

After the `dispatcher.py` script has finished executing, you can check the number of running processes, as EC2 nodes continue running until they have finished all their assigned work, at which point they terminate. One way to check the status of the EC2 nodes is logging onto the AWS console, selecting "EC2" and "Running Instances". Another way is running python interactively from this folder and then running `import cloud_setup` and then `cloud_setup.print_num_running()`.

If there is no progress, then you can debug the run by logging onto one of the EC2 nodes as described in the previous section of this document. Debug output will be available in files `~/code/screen_output.txt`. Once you are finished debugging, you can terminate all running instances from the AWS console by navigating to "EC2" and "Running Instances", selecting all the instances, right clicking, and selecting "Instance State -> Terminate".

### Advanced - Updating tags during the run

If you want to keep track of how far along each job is, you can call the helper script `update_tags.py` from within your script. This file should be called as follows:

```
python ~/update_tags.py key value
```

This will add (or update) the tag `key` to have value `value`. These tags can be displayed on the AWS console by adding the relevant tags as columns on the console page.

For example, you might want to keep track the percentage of work completed as the job runs. Your script should run the command

```
python ~/update_tags.py percent_complete <value>
```

to update the `percent_complete` tag with the updated percentage of work complete. You will then be able to see this value in the list of running instances in the AWS console to get an idea of how far along each job is, and provide some assurance that work is still progressing.

## Internals

Though we do not expect that most researchers will need to modify the internals of the AWS testing infrastructure, we provide details for completeness. As indicated in the previous sections, cloud runs are started with `dispatcher.py`. This script performs a number of steps:

1. Validates that the command-line options are properly specified, that the `.boto` credentials file is present, the `GUROBI_CLOUD_KEY.txt` file exists, and that the script is run from the `aws-runner` directory.
2. Performs setup related to Gurobi AWS. Queries the Gurobi website for the latest AMI for the given AWS region, and forms the `user_data` that is required for adding the Gurobi license key to the AWS instances on startup.
3. Performs several startup tasks. The `cloud_setup.create_security_group` function is used to create an AWS security group (if one has not already been created) that allows SSH access to the EC2 nodes from any IP address on port 22. The `cloud_setup.create_keypair` function is used to create a key for the account's user (if one has not already been created), which is stored in `~/.ssh/<jobname>.pem`. The `cloud_setup.clean_known_hosts` function is used to remove any EC2 hosts from the `~/.ssh/known_hosts` file, which prevents SSH errors due to hostname collisions in consecutive large runs. Finally, the `cloud_setup.wait_for_shutdown` function waits for all nodes that are currently shutting down to be terminated.
3. Creates the EC2 instances using the `create_instances` function (this step is skipped if the `nocreate` command-line argument is provided). This is a thin wrapper around the `cloud_setup.launch_instance` function, which is called in parallel using the `multiprocessing` package for efficiency purposes.
4. Creates connections to all the instances using the `connect_instances` function. This is a thin wrapper around the `cloud_setup.connect_instance` function. The function returns an SSH client that can be used to connect to each of the instances.
5. Sets up all the instances using the `setup_instances` function (this step is skipped if the `nocreate` command-line argument is provided). This copies `.boto`, `INSTALL.py`, and `INSTALL.sh` from your local `aws-runner` folder to the instance (along with `cloud_setup.py`, `update_tags.py` for updating tags during the run, and `save_results.py` for uploading results to SimpleDB). It also copies the specified code folder from your local computer to the instance. It then runs the `INSTALL.py` script, which runs in an infinite loop, running `INSTALL.sh` with a 6-minute timeout until the setup is complete.
7. Starts a run on all EC2 nodes using the `dispatch_and_run` function (this step is skipped if the `nodispatch` command-line argument is provided). Communicates with each EC2 node which command it should run and creates a shell script to run this command followed by the helper script to save the results in SimpleDB. Finally, `dispatch_and_run` executes this script on each node.
8. Terminates once work has been dispatched to all EC2 nodes.
