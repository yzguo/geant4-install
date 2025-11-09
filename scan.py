#!/usr/bin/env python3
# filesystem_audit.py
# Purpose: Scan entire Linux filesystem as root, collect file metadata,
#          skip virtual/network mounts, write to CSV in chunks,
#          and generate interactive time-based visualization.
# Handles non-UTF-8 filenames via percent-encoding to ensure CSV validity.

import os
import sys
import csv
import time
import stat
import urllib.parse
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots


# Filesystem types to skip (virtual and network)
SKIP_FS_TYPES = {
    'proc', 'sysfs', 'devtmpfs', 'tmpfs', 'devpts', 'cgroup', 'cgroup2',
    'pstore', 'efivarfs', 'bpf', 'securityfs', 'debugfs', 'tracefs',
    'fusectl', 'mqueue', 'hugetlbfs', 'autofs', 'overlay',
    'nfs', 'nfs4', 'cifs', 'smb3', 'smbfs', 'fuse.sshfs', 'glusterfs',
    'lustre', '9p', 'afs'
}


def get_mount_points():
    """Read /proc/mounts and return dict: {mount_point: fs_type}."""
    mounts = {}
    try:
        with open('/proc/mounts', 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount_point = parts[1]
                fs_type = parts[2]
                mounts[mount_point] = fs_type
    except Exception as e:
        print(f"[WARNING] Failed to read /proc/mounts: {e}", file=sys.stderr)
    return mounts


def should_skip_path_bytes(path_bytes, mount_info):
    """
    Determine if a file (given as raw bytes path) resides on a skipped filesystem.
    Uses os.fsdecode to safely convert to string for mount resolution.
    """
    try:
        # Convert to system string (may contain surrogates, but that's okay for Path)
        path_str = os.fsdecode(path_bytes)
        resolved = Path(path_str).resolve()
        resolved_str = str(resolved)
    except (OSError, RuntimeError, ValueError, UnicodeError):
        # If resolution fails, skip to be safe
        return True

    # Find the most specific mount point that is a prefix
    matching_mounts = [mp for mp in mount_info if resolved_str.startswith(mp)]
    if not matching_mounts:
        return False

    best_match = max(matching_mounts, key=len)
    fs_type = mount_info[best_match]
    return fs_type in SKIP_FS_TYPES


def encode_path_for_csv(path_bytes):
    """
    Encode raw filesystem path bytes into a UTF-8 safe, reversible string.
    Uses percent-encoding (like URLs), preserving all original bytes.
    Safe for CSV and human-readable in many cases.
    """
    return urllib.parse.quote_from_bytes(path_bytes, safe='/')


def collect_file_metadata(root_path=b'/', chunk_size=100000, csv_path='filesystem_audit.csv'):
    """
    Recursively walk filesystem starting from root (as bytes),
    collect regular file metadata, skip unwanted mounts,
    and write to CSV in chunks.
    """
    if os.geteuid() != 0:
        print("[ERROR] This script must be run as root.", file=sys.stderr)
        sys.exit(1)

    mount_info = get_mount_points()
    processed = 0
    buffer = []

    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['path', 'size_bytes', 'mtime', 'atime'])
        writer.writeheader()

        try:
            for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
                # Skip entire subtree if on excluded filesystem
                if should_skip_path_bytes(dirpath, mount_info):
                    dirnames[:] = []  # prune search
                    continue

                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        # Use lstat to avoid following symlinks
                        st = os.lstat(filepath)
                        if not stat.S_ISREG(st.st_mode):
                            continue

                        # Double-check: skip if file is on excluded mount
                        if should_skip_path_bytes(filepath, mount_info):
                            continue

                        safe_path = encode_path_for_csv(filepath)
                        buffer.append({
                            'path': safe_path,
                            'size_bytes': st.st_size,
                            'mtime': st.st_mtime,
                            'atime': st.st_atime
                        })
                        processed += 1

                        if len(buffer) >= chunk_size:
                            writer.writerows(buffer)
                            csvfile.flush()
                            buffer.clear()
                            print(f"[INFO] Processed {processed} files...", file=sys.stderr)

                    except (OSError, IOError):
                        # Skip files that can't be accessed (e.g., permission denied)
                        continue

        except KeyboardInterrupt:
            print("\n[INFO] Scan interrupted by user.", file=sys.stderr)

        # Write remaining entries
        if buffer:
            writer.writerows(buffer)
            print(f"[INFO] Final batch written. Total files: {processed}", file=sys.stderr)

    return csv_path


def create_visualization(csv_path):
    """Generate interactive Plotly HTML report with monthly aggregation."""
    print("[INFO] Loading CSV data for visualization...", file=sys.stderr)
    try:
        df = pd.read_csv(csv_path, dtype={'path': 'string', 'size_bytes': 'int64'})
    except Exception as e:
        print(f"[ERROR] Failed to read CSV: {e}", file=sys.stderr)
        return

    # Convert timestamps
    df['mtime_dt'] = pd.to_datetime(df['mtime'], unit='s', errors='coerce')
    df['atime_dt'] = pd.to_datetime(df['atime'], unit='s', errors='coerce')
    df = df.dropna(subset=['mtime_dt', 'atime_dt'])

    # Monthly bins
    df['mtime_month'] = df['mtime_dt'].dt.to_period('M').astype(str)
    df['atime_month'] = df['atime_dt'].dt.to_period('M').astype(str)

    # Aggregate
    mtime_agg = df.groupby('mtime_month').agg(
        file_count=('mtime', 'count'),
        total_size=('size_bytes', 'sum')
    ).reset_index()

    atime_agg = df.groupby('atime_month').agg(
        file_count=('atime', 'count'),
        total_size=('size_bytes', 'sum')
    ).reset_index()

    # Align months
    all_months = sorted(set(mtime_agg['mtime_month']) | set(atime_agg['atime_month']))
    if not all_months:
        print("[WARNING] No valid time data found for visualization.", file=sys.stderr)
        return

    mtime_agg = mtime_agg.set_index('mtime_month').reindex(all_months, fill_value=0).reset_index()
    atime_agg = atime_agg.set_index('atime_month').reindex(all_months, fill_value=0).reset_index()

    # Plot
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            'File Count by Modification Time',
            'File Count by Access Time',
            'Total Size by Modification Time',
            'Total Size by Access Time'
        )
    )

    fig.add_trace(px.bar(mtime_agg, x='mtime_month', y='file_count').data[0], row=1, col=1)
    fig.add_trace(px.bar(atime_agg, x='atime_month', y='file_count').data[0], row=1, col=2)
    fig.add_trace(px.bar(mtime_agg, x='mtime_month', y='total_size').data[0], row=2, col=1)
    fig.add_trace(px.bar(atime_agg, x='atime_month', y='total_size').data[0], row=2, col=2)

    fig.update_layout(
        title="Filesystem Audit Report (Time Distribution)",
        height=900,
        showlegend=False,
        hovermode='x unified'
    )

    output_html = 'filesystem_audit.html'
    fig.write_html(output_html)
    print(f"[INFO] Visualization saved to {output_html}", file=sys.stderr)

    # Optional: Save monthly drill-down CSVs (optional, can be large)
    drill_dir = Path('drilldown_data')
    drill_dir.mkdir(exist_ok=True)
    for month in all_months:
        if month == '0':
            continue
        mod_subset = df[df['mtime_month'] == month]
        if not mod_subset.empty:
            mod_subset.to_csv(drill_dir / f"modified_{month}.csv", index=False)
        acc_subset = df[df['atime_month'] == month]
        if not acc_subset.empty:
            acc_subset.to_csv(drill_dir / f"accessed_{month}.csv", index=False)
    print(f"[INFO] Monthly drill-down files saved in '{drill_dir}'", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Audit Linux filesystem as root.")
    parser.add_argument('--output', '-o', default='filesystem_audit.csv',
                        help='Output CSV path (default: filesystem_audit.csv)')
    parser.add_argument('--chunk-size', type=int, default=100000,
                        help='Number of records per write chunk (default: 100000)')
    parser.add_argument('--no-viz', action='store_true', help='Skip visualization')
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("[ERROR] Must run as root.", file=sys.stderr)
        sys.exit(1)

    print("[INFO] Starting filesystem scan. This may take a long time.", file=sys.stderr)
    csv_file = collect_file_metadata(root_path=b'/', chunk_size=args.chunk_size, csv_path=args.output)

    if not args.no_viz:
        create_visualization(csv_file)

    print("[INFO] Audit completed successfully.", file=sys.stderr)


if __name__ == '__main__':
    main()