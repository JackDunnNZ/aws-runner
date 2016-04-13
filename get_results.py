# python grabFullRuns.py
import csv
import sys
import cloud_setup


def write_results(results, results_file):
    header_line = None

    with open(results_file, "w") as f:
        writer = csv.writer(f)

        for result in results:
            if not header_line:
                header_line = result.keys()
                writer.writerow(header_line)

            output_line = []
            for col in header_line:
                output_line.append(result[col])
            writer.writerow(output_line)

if __name__ == "__main__":
    # Validate command-line arguments
    if len(sys.argv) == 3:
        job = sys.argv[1]
        sdb, dom = cloud_setup.setup_sdb_domain(job)
        rs = dom.select('select * from `%s`' % job)
        write_results(rs.itervalues(), sys.argv[2])
    elif len(sys.argv) == 2:
        print "No outfile specified: dumping to stdout"
        cloud_setup.dump_sdb_domain(sys.argv[1])
        exit(0)
    else:
        print "Usage: python get_results.py jobname [output_file]"
        exit(1)
