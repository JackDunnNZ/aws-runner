import csv
import time
import sys
import cloud_setup


def get_results_from_csv(key, job, tag, results_file, current_time):
    # Read from output file
    reader = csv.reader(open(results_file, "rU"))
    header_line = reader.next()
    num_cols = len(header_line)

    results = {}
    for row_num, line in enumerate(reader):
        rowkey = "%s-%d" % (key, row_num)
        values = {
            "AWS_job": job,
            "AWS_tag": tag,
            "AWS_timestamp": current_time,
            "AWS_row_num": row_num,
        }
        for col in xrange(num_cols):
            values[header_line[col]] = line[col]
        results[rowkey] = values
    return results


def save_results(job, tag, results_file):
    try:
        current_time = time.time()
        key = "%s-%s-%f" % (job, tag, current_time)

        # Save file to s3
        s3, bucket = cloud_setup.setup_s3_bucket(job)
        cloud_setup.add_file_to_s3_bucket(bucket, key, results_file)

        # Get ready for SimpleDB comms
        sdb, dom = cloud_setup.setup_sdb_domain(job)

        results = get_results_from_csv(key, job, tag, results_file,
                                       current_time)

        # Write to SDB
        dom.batch_put_attributes(results)
    finally:
        # Self-terminate at completion
        cloud_setup.terminate_instance(tag)

if __name__ == "__main__":
    # Validate command-line arguments
    if len(sys.argv) != 4:
        print "Usage: python save_results.py job tag results_file"
        exit(1)
    save_results(sys.argv[1], sys.argv[2], sys.argv[3])
