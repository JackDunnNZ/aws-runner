# python get_s3_files.py
import sys
import cloud_setup

if __name__ == "__main__":
    # Validate command-line arguments
    if len(sys.argv) == 3:
        job = sys.argv[1]
        output_folder = sys.argv[2]
        cloud_setup.download_s3_bucket(job, output_folder)
    else:
        print "Usage: python get_s3_files.py jobname output_folder"
        exit(1)
