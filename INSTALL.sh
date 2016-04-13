#!/bin/bash
# INSTALL.sh
# Install the dependencies required to run on a Gurobi-Ubuntu EC2 instance

# Args:
# $1: iteration number

###############################################################################
### APT--GET-CONFIG

# Julia apt-get config
sudo add-apt-repository ppa:staticfloat/juliareleases --yes > progress_A_3_$1.txt 2>&1
sudo add-apt-repository ppa:staticfloat/julia-deps --yes > progress_A_4_$1.txt 2>&1

# R apt-get config
sudo su -c "echo 'deb http://cran.case.edu/bin/linux/ubuntu trusty/' >> /etc/apt/sources.list" > progress_A_1_$1.txt 2>&1
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys E084DAB9 > progress_A_2_$1.txt 2>&1

###############################################################################
### APT-GET-EVERYTHING

sudo apt-get update --yes > progress_B_1_$1.txt 2>&1

# Base things
sudo apt-get -y --force-yes install git python-pip python-paramiko > progress_B_2_$1.txt 2>&1

# Julia
sudo apt-get -y --force-yes install julia > progress_B_3_$1.txt 2>&1

# R
sudo apt-get -y --force-yes install r-base r-recommended r-base-dev r-base-core r-cran-randomforest > progress_B_4_$1.txt 2>&1

###############################################################################
### LANGUAGE PACKAGE CONFIG

# Add base packages
sudo pip install boto > progress_C_1_$1.txt 2>&1

# Add Julia packages
julia -e 'Pkg.update(); \
    Pkg.add("ArgParse"); \
    Pkg.add("DataFrames"); \
    Pkg.add("MLBase"); \
    Pkg.add("JuMP"); \
    Pkg.add("Gurobi"); \
println("Done")' > progress_C_2_$1.txt 2>&1

# Add R packages
#   already installed with apt-get

###############################################################################
### CHECK EVERYTHING IS WORKING
julia -e 'Pkg.build("Gurobi")' > progress_D_1_$1.txt 2>&1
julia -e 'using Gurobi; println(Gurobi.version)' > GUROBI_VERSION
