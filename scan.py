#!/usr/bin/env python3
# filesystem_audit.py
# Author: Auto-generated for secure filesystem audit
# Purpose: Scan entire filesystem (excluding virtual/network mounts), collect file metadata,
#          write to CSV in chunks, and generate an interactive time-based visualization.

import os
import sys
import csv
import time
import stat
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# List of filesystem types to skip (common virtual and network filesystems)
SKIP_FS_TYPES = {
    'proc', 'sysfs', 'devtmpfs', 'tmpfs', 'devpts', 'cgroup', 'cgroup2',
    'pstore', 'efivarfs', 'bpf', 'securityfs', 'debugfs', 'tracefs',
    'fusectl', 'mqueue', 'hugetlbfs', 'autofs', 'overlay',
    'nfs', 'nfs4', 'cifs', 'smb3', 'smbfs', 'fuse.sshfs', 'glusterfs',
    'lustre', '9p', 'afs'
}


def get_mount_points():
    """Get dictionary of mount points and their filesystem types."""
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


def should_skip_path(path_str, mount_info):
    """Determine if a path belongs to a skipped filesystem."""
    path = Path(path_str)
    # Ensure absolute path
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return True  # skip if resolution fails

    # Find the deepest mount point that is a prefix of this path
    matching_mounts = [mp for mp in mount_info if str(resolved).startswith(mp)]
    if not matching_mounts:
        return False  # unlikely, but safe to scan

    # Choose the longest (most specific) mount point
    best_match = max(matching_mounts, key=len)
    fs_type = mount_info[best_match]

    return fs_type in SKIP_FS_TYPES


def safe_decode_path(path_bytes):
    """Safely decode a filesystem path that may contain non-UTF-8 bytes."""
    try:
        return path_bytes.decode('utf-8')
    except UnicodeDecodeError:
        # Replace invalid bytes to produce a valid string
        return path_bytes.decode('utf-8', errors='replace')


def collect_file_metadata(root_path='/', chunk_size=100000, csv_path='filesystem_audit.csv'):
    """Recursively scan filesystem and write file metadata to CSV in chunks."""
    if os.geteuid() != 0:
        print("[ERROR] This script must be run as root.", file=sys.stderr)
        sys.exit(1)

    mount_info = get_mount_points()

    # Open CSV file for writing
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['path', 'size_bytes', 'mtime', 'atime']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        buffer = []
        file_count = 0

        try:
            for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
                # Modify dirnames in-place to skip problematic subdirs early
                # This does NOT fully prevent entry if mount info is missing,
                # but improves performance.
                if should_skip_path(dirpath, mount_info):
                    dirnames[:] = []  # prune search
                    continue

                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)

                    try:
                        # Use os.lstat to avoid following symlinks
                        st = os.lstat(filepath)
                        # Skip non-regular files (e.g., symlinks, devices)
                        if not stat.S_ISREG(st.st_mode):
                            continue

                        # Double-check mount after file discovery (for bind mounts, etc.)
                        if should_skip_path(filepath, mount_info):
                            continue

                        size = st.st_size
                        mtime = st.st_mtime
                        atime = st.st_atime

                        # Safely handle path encoding
                        if isinstance(filepath, bytes):
                            path_str = safe_decode_path(filepath)
                        else:
                            path_str = filepath

                        buffer.append({
                            'path': path_str,
                            'size_bytes': size,
                            'mtime': mtime,
                            'atime': atime
                        })
                        file_count += 1

                        if len(buffer) >= chunk_size:
                            writer.writerows(buffer)
                            csvfile.flush()  # ensure write to disk
                            buffer.clear()
                            print(f"[INFO] Processed {file_count} files...", file=sys.stderr)

                    except (OSError, IOError) as e:
                        # Skip inaccessible files (e.g., permission denied, broken links)
                        continue

        except KeyboardInterrupt:
            print("\n[INFO] Scan interrupted by user.", file=sys.stderr)

        # Write remaining buffer
        if buffer:
            writer.writerows(buffer)
            print(f"[INFO] Final write: total files = {file_count}", file=sys.stderr)

    return csv_path


def create_visualization(csv_path):
    """Create interactive Plotly visualization with monthly drill-down."""
    print("[INFO] Loading data for visualization...", file=sys.stderr)
    df = pd.read_csv(csv_path, dtype={'path': 'string', 'size_bytes': 'int64'})

    # Convert timestamps to datetime
    df['mtime_dt'] = pd.to_datetime(df['mtime'], unit='s')
    df['atime_dt'] = pd.to_datetime(df['atime'], unit='s')

    # Create monthly bins
    df['mtime_month'] = df['mtime_dt'].dt.to_period('M').astype(str)
    df['atime_month'] = df['atime_dt'].dt.to_period('M').astype(str)

    # Aggregate by month
    mtime_agg = df.groupby('mtime_month').agg(
        file_count=('mtime', 'count'),
        total_size=('size_bytes', 'sum')
    ).reset_index()

    atime_agg = df.groupby('atime_month').agg(
        file_count=('atime', 'count'),
        total_size=('size_bytes', 'sum')
    ).reset_index()

    # Ensure consistent month order
    all_months = sorted(set(mtime_agg['mtime_month']) | set(atime_agg['atime_month']))
    mtime_agg = mtime_agg.set_index('mtime_month').reindex(all_months, fill_value=0).reset_index()
    atime_agg = atime_agg.set_index('atime_month').reindex(all_months, fill_value=0).reset_index()

    # Create interactive plot
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            'Files by Modification Time (Count)',
            'Files by Access Time (Count)',
            'Files by Modification Time (Total Size)',
            'Files by Access Time (Total Size)'
        ),
        specs=[[{"secondary_y": False}, {"secondary_y": False}],
               [{"secondary_y": False}, {"secondary_y": False}]]
    )

    # Counts
    fig.add_trace(go.Bar(x=mtime_agg['mtime_month'], y=mtime_agg['file_count'], name='Mod Count'), row=1, col=1)
    fig.add_trace(go.Bar(x=atime_agg['atime_month'], y=atime_agg['file_count'], name='Access Count'), row=1, col=2)

    # Sizes
    fig.add_trace(go.Bar(x=mtime_agg['mtime_month'], y=mtime_agg['total_size'], name='Mod Size'), row=2, col=1)
    fig.add_trace(go.Bar(x=atime_agg['atime_month'], y=atime_agg['total_size'], name='Access Size'), row=2, col=2)

    fig.update_layout(
        title="Filesystem Audit: Time-Based Distribution",
        height=800,
        showlegend=False,
        hovermode='x unified'
    )

    # Add click interaction: on bar click, show all files in that month
    # Note: Plotly itself doesn’t support drill-down to raw data natively in static HTML,
    # but we can embed file listings in hover or suggest exporting data.
    # For true interactivity (e.g., clicking to list files), a Dash app would be needed.
    # As a practical compromise, we save monthly listings to a parquet or CSV for inspection.

    # Save monthly file listings for drill-down
    drilldown_dir = 'drilldown_data'
    Path(drilldown_dir).mkdir(exist_ok=True)

    for month in all_months:
        if month == '0':
            continue
        # Modification-based
        mod_files = df[df['mtime_month'] == month]
        if not mod_files.empty:
            mod_files[['path', 'size_bytes', 'mtime', 'atime']].to_csv(
                f"{drilldown_dir}/mod_{month}.csv", index=False
            )
        # Access-based
        acc_files = df[df['atime_month'] == month]
        if not acc_files.empty:
            acc_files[['path', 'size_bytes', 'mtime', 'atime']].to_csv(
                f"{drilldown_dir}/access_{month}.csv", index=False
            )

    # Save HTML
    output_html = 'filesystem_audit.html'
    fig.write_html(output_html)
    print(f"[INFO] Visualization saved to {output_html}", file=sys.stderr)
    print(f"[INFO] Monthly file listings saved in '{drilldown_dir}' directory for detailed inspection.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Audit Linux filesystem as root and generate visualization.")
    parser.add_argument('--output', '-o', default='filesystem_audit.csv',
                        help='Output CSV file path (default: filesystem_audit.csv)')
    parser.add_argument('--chunk-size', type=int, default=100000,
                        help='Number of records per write chunk (default: 100000)')
    parser.add_argument('--no-viz', action='store_true',
                        help='Skip visualization step')
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("[ERROR] This script must be run as root.", file=sys.stderr)
        sys.exit(1)

    print("[INFO] Starting filesystem scan. This may take a long time on large systems...", file=sys.stderr)
    csv_path = collect_file_metadata(root_path='/', chunk_size=args.chunk_size, csv_path=args.output)

    if not args.no_viz:
        create_visualization(csv_path)

    print("[INFO] Done.", file=sys.stderr)


if __name__ == '__main__':
    main()
