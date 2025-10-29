#!/usr/bin/env python3
import os
import sys
import time
import csv
import stat
import datetime
from pathlib import Path
import subprocess
import pandas as pd
import matplotlib.pyplot as plt

# Configuration
ROOT_PATH = "/"
OUTPUT_CSV = "file_scan.csv"
CHUNK_SIZE = 100_000
SMALL_FILE_THRESHOLD = 10 * 1024 * 1024      # 10 MB
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024     # 100 MB

def get_mount_points():
    mount_info = {}
    try:
        result = subprocess.run(['findmnt', '-n', '-o', 'TARGET,FSTYPE'], capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    target = parts[0]
                    fstype = parts[1]
                    mount_info[target] = fstype
    except Exception as e:
        print(f"[Warning] Can't get mount info: {e}", file=sys.stderr)
    return mount_info

def should_skip(path_str, mount_info):
    path = Path(path_str)
    for mount_point, fstype in mount_info.items():
        try:
            if path.is_relative_to(mount_point):
                if any(fs in fstype.lower() for fs in ['nfs', 'cifs', 'smb', 'proc', 'sysfs', 'devtmpfs', 'tmpfs', 'overlay', 'fuse', 'autofs']):
                    return True
        except ValueError:
            continue
    return False

def safe_stat(path):
    try:
        return os.lstat(path)
    except (OSError, IOError):
        return None

def first_pass_collect_files_and_build_dir_sizes(root, mount_info):
    """
    First pass: traverse all files, collect file info, and build directory sizes.
    Returns:
        files_info: list of file records (for stats & later output)
        dir_sizes: dict {dir_path: total_size}
    """
    files_info = []
    dir_sizes = {}
    small_count = 0
    large_count = 0

    print("First pass: traverse all files and calculate directory sizes...")
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Skip mount points
        dirnames[:] = [d for d in dirnames if not should_skip(os.path.join(dirpath, d), mount_info)]

        # Process files
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            st = safe_stat(filepath)
            if st is None or not stat.S_ISREG(st.st_mode):
                continue

            size = st.st_size
            atime = st.st_atime
            mtime = st.st_mtime
            ctime = st.st_ctime

            # Update directory sizes (all parent directories)
            current = dirpath
            while True:
                dir_sizes[current] = dir_sizes.get(current, 0) + size
                if current == ROOT_PATH:
                    break
                parent = os.path.dirname(current)
                if parent == current:  # Prevent infinite loop at root
                    break
                current = parent

            # File statistics
            if size < SMALL_FILE_THRESHOLD:
                small_count += 1
            if size > LARGE_FILE_THRESHOLD:
                large_count += 1

            files_info.append({
                'name': filename,
                'absolute_path': filepath,
                'access_time': datetime.datetime.fromtimestamp(atime).isoformat(),
                'modification_time': datetime.datetime.fromtimestamp(mtime).isoformat(),
                'change_time': datetime.datetime.fromtimestamp(ctime).isoformat(),
                'size_bytes': size,
                'is_file': True
            })

    return files_info, dir_sizes, small_count, large_count

def generate_all_records(root, mount_info, dir_sizes, files_info):
    """Generator: yield directory records + file records in order"""
    # First yield all directories (sorted by path to ensure parent-child relationships are clear)
    print("Generating directory records...")
    sorted_dirs = sorted(dir_sizes.keys())
    for d in sorted_dirs:
        if should_skip(d, mount_info):
            continue
        st = safe_stat(d)
        if st is None:
            ctime = mtime = 0.0
        else:
            atime = st.st_atime
            mtime = st.st_mtime
            ctime = st.st_ctime
        yield {
            'name': os.path.basename(d) or '/',
            'absolute_path': d,
            'access_time': datetime.datetime.fromtimestamp(atime).isoformat(),
            'modification_time': datetime.datetime.fromtimestamp(mtime).isoformat(),
            'change_time': datetime.datetime.fromtimestamp(ctime).isoformat(),
            'size_bytes': dir_sizes[d],
            'is_file': False
        }

    # Then yield all files
    print("Generating file records...")
    for f in files_info:
        yield f

def write_records_in_chunks(generator, output_file, chunk_size=CHUNK_SIZE):
    """Write CSV in chunks to avoid memory overflow"""
    first = True
    chunk = []
    count = 0

    for record in generator:
        chunk.append(record)
        count += 1
        if len(chunk) >= chunk_size:
            _write_chunk(output_file, chunk, first)
            first = False
            chunk = []
            print(f"Written {count} records so far...")

    # Write remaining records
    if chunk:
        _write_chunk(output_file, chunk, first)
        print(f"Total written records: {count}.")

def _write_chunk(output_file, chunk, write_header):
    fieldnames = ['name', 'absolute_path', 'access_time', 'modification_time', 'change_time', 'size_bytes', 'is_file']
    with open(output_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        # Clean invalid UTF-8 characters
        safe_chunk = []
        for rec in chunk:
            safe_rec = {}
            for key, val in rec.items():
                if isinstance(val, str):
                    # Replace invalid UTF-8 characters with ?
                    safe_rec[key] = val.encode('utf-8', errors='replace').decode('utf-8')
                else:
                    safe_rec[key] = val
            safe_chunk.append(safe_rec)
        writer.writerows(safe_chunk)

def plot_time_series(df, time_col, title_suffix, filename):
    if df.empty:
        print(f"No data for {title_suffix}.")
        return

    df['time_dt'] = pd.to_datetime(df[time_col], format='ISO8601')
    
    current_time = pd.Timestamp.now()
    five_years_ago = current_time - pd.DateOffset(years=5)
    df_recent = df[df['time_dt'] >= five_years_ago]

    if df_recent.empty:
        print(f"No data in last 5 years for {title_suffix}.")
        return

    df_recent['year_month'] = df_recent['time_dt'].dt.to_period('M')
    
    # Count and total size per month
    monthly_stats = df_recent.groupby('year_month').agg(
        file_count=('size_bytes', 'size'),
        total_size=('size_bytes', 'sum')
    ).reset_index()

    x_dates = monthly_stats['year_month'].dt.to_timestamp()
    counts = monthly_stats['file_count']
    sizes = monthly_stats['total_size']

    fig, ax1 = plt.subplots(figsize=(20, 8))

    color = 'tab:blue'
    ax1.set_xlabel('Year', fontsize=12)
    ax1.set_ylabel('File Count', color=color, fontsize=12)
    ax1.bar(x_dates, counts, color=color, width=25, alpha=0.6, label='File Count')
    ax1.tick_params(axis='y', labelcolor=color)

    ax2 = ax1.twinx()
    color = 'tab:red'
    ax2.set_ylabel('Total Size (Bytes)', color=color, fontsize=12)
    ax2.plot(x_dates, sizes, color=color, marker='o', linewidth=2, label='Total Size')
    ax2.tick_params(axis='y', labelcolor=color)

    ax1.set_xlim(five_years_ago, current_time)
    ax1.xaxis.set_major_locator(plt.matplotlib.dates.YearLocator())
    ax1.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y'))
    ax1.xaxis.set_minor_locator(plt.matplotlib.dates.MonthLocator(interval=3))

    plt.setp(ax1.get_xticklabels(), rotation=0, ha='center', fontsize=12)
    plt.title(f'File Activity by {title_suffix} (Last 5 Years)', fontsize=14)
    fig.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"Chart saved: {filename}")

def main():
    if os.geteuid() != 0:
        print("Root privileges are required!", file=sys.stderr)
        sys.exit(1)

    print("Getting mount point information...")
    mount_info = get_mount_points()

    start_time = time.time()
    files_info, dir_sizes, small_count, large_count = first_pass_collect_files_and_build_dir_sizes(ROOT_PATH, mount_info)

    print(f"\nFile statistics completed:")
    print(f"  Small files (<10MB): {small_count}")
    print(f"  Large files (>100MB): {large_count}")
    print(f"  Total files: {len(files_info)}")
    print(f"  Total directories: {len(dir_sizes)}")

    with open('file_statistics.txt', 'w') as stats_file:
        stats_file.write(f"Small files (<10MB): {small_count}\n")
        stats_file.write(f"Large files (>100MB): {large_count}\n")
        stats_file.write(f"Total files: {len(files_info)}\n")
        stats_file.write(f"Total directories: {len(dir_sizes)}\n")

    # Generate all records
    record_gen = generate_all_records(ROOT_PATH, mount_info, dir_sizes, files_info)

    # Write CSV in chunks
    if os.path.exists(OUTPUT_CSV):
        os.remove(OUTPUT_CSV)  # Ensure it's a new file
    write_records_in_chunks(record_gen, OUTPUT_CSV, CHUNK_SIZE)

    # Convert files_info to DataFrame for plotting (only files)
    if files_info:
        df_files = pd.DataFrame(files_info)

        # Plot by access time
        plot_time_series(df_files, 'access_time', 'Last Access Time', 'file_access_timeline.png')

        # Plot by modification time
        plot_time_series(df_files, 'modification_time', 'Last Modification Time', 'file_modification_timeline.png')
    else:
        print("No file data to plot.")

    elapsed = time.time() - start_time
    print(f"\nAll tasks completed! Total time: {elapsed:.2f} seconds")
    print(f"Result file: {OUTPUT_CSV}")
    print("Visualization charts: file_access_timeline.png, file_modification_timeline.png")

if __name__ == "__main__":
    main()
