"""Create all three DLP sample datasets in one go.

    python make_all_datasets.py                    # high, medium and low (about 10 minutes, ~1.5 GB)
    python make_all_datasets.py --sets low medium  # only some of them

Each set is 50 .txt files from 2 KB to 100 MB, with manifest.csv, answer_key.csv
and an answer_key/ folder, written next to this script:

    dlp_samples_high     almost every line holds sensitive data (make_dlp_test_files.py)
    dlp_samples_medium   about one sensitive value per KB      (make_dlp_low_density_files.py --density medium)
    dlp_samples_low      1 to 5 sensitive values per file      (make_dlp_low_density_files.py)

The output is the same every time. Needs only Python 3 (no extra packages) and the two
generator scripts in the same folder as this one.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SETS = {
    "high":   ["make_dlp_test_files.py"],
    "medium": ["make_dlp_low_density_files.py", "--density", "medium"],
    "low":    ["make_dlp_low_density_files.py"],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets", nargs="+", choices=list(SETS), default=list(SETS),
                    help="which datasets to create (default: all three)")
    args = ap.parse_args()

    for script in {cmd[0] for cmd in SETS.values()}:
        if not os.path.exists(os.path.join(HERE, script)):
            sys.exit(f"{script} is missing: keep it in the same folder as this script.")

    started = time.time()
    for name in args.sets:
        print(f"\n=== Creating dlp_samples_{name} ===", flush=True)
        t = time.time()
        result = subprocess.run([sys.executable, *SETS[name]], cwd=HERE)
        if result.returncode != 0:
            sys.exit(f"dlp_samples_{name} failed (exit code {result.returncode}); the other sets were not changed.")
        print(f"dlp_samples_{name} done in {time.time() - t:.0f} s", flush=True)
    print(f"\nAll done in {(time.time() - started) / 60:.1f} min: "
          + ", ".join(f"dlp_samples_{n}" for n in args.sets), flush=True)


if __name__ == "__main__":
    main()
