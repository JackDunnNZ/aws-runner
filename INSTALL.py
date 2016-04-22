import os.path
import re
import subprocess


def main():
    # Run installation script until it works (sometimes it takes more than once
    # due to apt-get servers not working, etc.)
    iteration = 0
    while True:
        iteration += 1
        try:
            p = subprocess.Popen(
                ["timeout", "360", "./INSTALL.sh", str(iteration)],
                stdout=None, stderr=None
            )
            p.wait()
        except:
            with open("failure.txt", "w") as f:
                f.write("INSTALL.py exited in failure\n")
            exit(1)

        if os.path.isfile("READY"):
            break

if __name__ == '__main__':
    main()
