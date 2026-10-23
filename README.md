# DLP evaluation

Send sample files to the DLP `/api/m/dlp/text/` endpoint and get an Excel report of how
long each file took and how accurately the DLP found the sensitive data in it.

## 1. Set up (once)

From this folder (Python 3.8 or later):

```bash
pip install -r requirements.txt
```

## 2. Create the sample files (once)

```bash
python make_all_datasets.py
```

This creates three folders of 50 files each (2 KB to 100 MB, about 10 minutes, 1.5 GB):

| Folder | Sensitive data in each file |
|---|---|
| `dlp_samples_high` | almost every line |
| `dlp_samples_medium` | about one value per KB |
| `dlp_samples_low` | 1 to 5 values |

Skip this step if the folders are already there.

## 3. Run the evaluation

Pick a folder:

```bash
python eval_dlp_text.py --dir dlp_samples_low
```

That sends every file in the folder once, smallest first, and prints each result as it
finishes:

```
[04] 04_astronomy_log_4KB.txt  run 1:  3.7s  OK  recall 80%  precision 80%  (4/5 found, 1 extra)
```

### Common options

| Option | What it does | Example |
|---|---|---|
| `--dir` | Folder to test | `--dir dlp_samples_medium` |
| `--runs` | Send each file this many times | `--runs 3` |
| `--only` | Only this file number (repeat for more) | `--only 27` |
| `--first` | Only the first N files | `--first 10` |
| `--from`, `--to` | A range of file numbers | `--from 20 --to 30` |
| `--timeout` | Seconds to wait for one file (default 600 = 10 min) | `--timeout 900` |
| `--stop-after-timeouts` | Stop after this many timeouts in a row (default 2) | `--stop-after-timeouts 1` |
| `--url` | Another server (default: QA) | `--url http://127.0.0.1:8000/api/m/dlp/text/` |
| `--token` | Bearer token, if the server requires one | `--token <token>` |

File numbers follow size order, the same as `#` in the report and the number at the start
of each file name.

Examples:

```bash
python eval_dlp_text.py --dir dlp_samples_high --first 10
python eval_dlp_text.py --dir dlp_samples_medium --only 27 --runs 3
python eval_dlp_text.py --dir dlp_samples_low --timeout 600 --stop-after-timeouts 1
```

## 4. Read the report

The report is saved in `reports\` as `<folder>_x<runs>.xlsx`, for example
`reports\dlp_samples_low_x1.xlsx`. It is updated after every file, so you can open it while
a run is still going (close it again before the next file finishes, or Windows blocks the update).

It has two sheets:

- **Summary**: files tested, requests succeeded, total and average time, and overall
  **recall**, **precision** and **F1**, with a short explanation of every column.
- **Results**: one row per file: size, time of each run, result, and how many sensitive
  values were planted, found correctly, missed and extra.

| Term | Meaning |
|---|---|
| Recall | Share of the planted sensitive values the DLP found |
| Precision | Share of what the DLP reported that was really planted |
| Extra | Values the DLP reported that the answer key does not list (in the high set, often real data such as job titles or transaction lines) |

## Good to know

- **Stopped or interrupted?** Run the same command again: files already done are skipped.
  Add `--retry-failed` to resend files that failed or timed out.
- **Rebuild the report without sending anything:** add `--report-only`.
- **Repeated runs** (`--runs 2` or more) are often faster after the first, because the
  server caches results. Run 1 is the real first-time figure.
- Each folder has its own `README.md` describing its files, and an `answer_key` folder
  listing every sensitive value planted in each file.
