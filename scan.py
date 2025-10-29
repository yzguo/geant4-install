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
                'creation_time': datetime.datetime.fromtimestamp(ctime).isoformat(),
                'last_modified_time': datetime.datetime.fromtimestamp(mtime).isoformat(),
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
            ctime = st.st_ctime
            mtime = st.st_mtime
        yield {
            'name': os.path.basename(d) or '/',
            'absolute_path': d,
            'creation_time': datetime.datetime.fromtimestamp(ctime).isoformat(),
            'last_modified_time': datetime.datetime.fromtimestamp(mtime).isoformat(),
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
    fieldnames = ['name', 'absolute_path', 'creation_time', 'last_modified_time', 'size_bytes', 'is_file']
    with open(output_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(chunk)

def plot_modification_timeline_from_files(files_info):
    if not files_info:
        print("No file data available for plotting.")
        return

    df = pd.DataFrame(files_info)
    df['mtime_dt'] = pd.to_datetime(df['last_modified_time'], format='ISO8601')

    current_time = pd.Timestamp.now()
    five_years_ago = current_time - pd.DateOffset(years=5)
    df_recent = df[df['mtime_dt'] >= five_years_ago]
    
    if df_recent.empty:
        print("No file data in the last 5 years for plotting.")
        return

    df['year_month'] = df['mtime_dt'].dt.to_period('M')
    monthly_counts = df['year_month'].value_counts().sort_index()

    x_dates = monthly_counts.index.to_timestamp() 
    y_values = monthly_counts.values

    start_date = five_years_ago
    end_date = current_time

    plt.figure(figsize=(20, 8))
    plt.bar(x_dates, y_values, color='lightgreen', width=25)

    # Set major ticks to "January of each year"
    ax = plt.gca()

    ax.xaxis.set_major_locator(plt.matplotlib.dates.YearLocator())
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y'))

    # Set minor ticks to "every quarter"
    ax.xaxis.set_minor_locator(plt.matplotlib.dates.MonthLocator(interval=3))

    ax.set_xlim(start_date, end_date)

    plt.setp(ax.get_xticklabels(), rotation=0, ha='center', fontsize=12, color='black')
    plt.setp(ax.get_xticklabels(minor=True), rotation=90, ha='right', fontsize=10, color='gray')
    plt.title('File Count by Last Modified Time (Last 5 Years)', fontsize=14)
    plt.xlabel('Year', fontsize=12)
    plt.ylabel('File Count', fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig('file_modification_timeline.png', dpi=150, bbox_inches='tight')
    print("Visualization chart saved as: file_modification_timeline.png")

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
    print(f"  Total directories: {len(dir_sizes)}")

    # Generate all records
    record_gen = generate_all_records(ROOT_PATH, mount_info, dir_sizes, files_info)

    # Write CSV in chunks
    if os.path.exists(OUTPUT_CSV):
        os.remove(OUTPUT_CSV)  # Ensure it's a new file
    write_records_in_chunks(record_gen, OUTPUT_CSV, CHUNK_SIZE)

    # Visualization (only with file information)
    plot_modification_timeline_from_files(files_info)

    elapsed = time.time() - start_time
    print(f"\nAll tasks completed! Total time: {elapsed:.2f} seconds")
    print(f"Result file: {OUTPUT_CSV}")
    print(f"Visualization chart: file_modification_timeline.png")

if __name__ == "__main__":
    main()
