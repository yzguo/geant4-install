#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File Inventory Scanner and Visualizer

Scans the entire filesystem from root recursively.
- Skips non-local filesystems (NFS, CIFS, FUSE, etc.)
- Collects: file path, size, mtime, atime
- Writes results incrementally to a CSV file
- Generates an interactive time-based visualization
- Handles non-UTF-8 filenames safely

Must be run as root to access all files.

Author: Yanzhen Guo
"""

import os
import sys
import csv
import time
import stat
import argparse
from pathlib import Path
from typing import Iterator, Tuple, Set

# Optional: for visualization
try:
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_VIS = True
except ImportError:
    HAS_VIS = False
    print("Warning: pandas or plotly not installed. Visualization will be skipped.", file=sys.stderr)


def is_root():
    """Check if script is running as root."""
    return os.geteuid() == 0


def get_local_filesystems() -> Set[str]:
    """
    Get set of mount points that are on local filesystems.
    Skips remote/network filesystems like nfs, cifs, fuse.*, etc.
    Uses /proc/mounts if available, fallback to /etc/mtab.
    """
    remote_fs_types = {
        'nfs', 'nfs4', 'cifs', 'smbfs', 'sshfs', 'fuse.sshfs',
        'glusterfs', 'lustre', 'afs', '9p', 'ceph', 'gcsfuse',
        's3fs', 'davfs', 'ftpfs'
    }

    local_mounts = set()
    candidates = ['/proc/mounts', '/etc/mtab']

    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    mount_point = parts[1]
                    fs_type = parts[2]
                    if fs_type not in remote_fs_types:
                        try:
                            # Normalize path and ensure it's absolute
                            resolved = os.path.realpath(mount_point)
                            local_mounts.add(resolved)
                        except (OSError, ValueError):
                            continue
            break  # prefer /proc/mounts
        except (OSError, IOError) as e:
            continue
    else:
        # Fallback: assume only '/' is local if no mount info
        local_mounts.add('/')

    return local_mounts


def is_on_local_fs(path: Path, local_mounts: Set[str]) -> bool:
    """Check if path is on a local filesystem."""
    try:
        path_abs = os.path.realpath(str(path))
    except (OSError, ValueError):
        return False

    # Check ancestors from deepest to root
    current = path_abs
    while current != '/':
        if current in local_mounts:
            return True
        current = os.path.dirname(current)
    return '/' in local_mounts


def safe_decode_path(path_bytes: bytes) -> str:
    """Safely decode a path that may contain invalid UTF-8."""
    try:
        return path_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return path_bytes.decode('utf-8', errors='replace')


def walk_files_safe(root_path: Path, local_mounts: Set[str]) -> Iterator[Tuple[str, int, float, float]]:
    """
    Recursively yield (path, size, mtime, atime) for regular files only.
    Skips directories, symlinks, devices, etc.
    Safely handles permission errors and non-UTF-8 paths.
    """
    try:
        with os.scandir(root_path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        # Recurse only if on local filesystem
                        if is_on_local_fs(Path(entry.path), local_mounts):
                            yield from walk_files_safe(Path(entry.path), local_mounts)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue

                    stat_info = entry.stat(follow_symlinks=False)
                    size = stat_info.st_size
                    mtime = stat_info.st_mtime
                    atime = stat_info.st_atime

                    # Get safe string path
                    if isinstance(entry.path, bytes):
                        path_str = safe_decode_path(entry.path)
                    else:
                        path_str = entry.path

                    yield (path_str, size, mtime, atime)

                except (OSError, IOError, ValueError):
                    # Skip inaccessible or corrupted entries
                    continue
    except (OSError, IOError, PermissionError):
        # Cannot read this directory; skip
        pass


def main():
    parser = argparse.ArgumentParser(description="Scan filesystem and generate inventory CSV + visualization.")
    parser.add_argument("-o", "--output", default="file_inventory.csv",
                        help="Output CSV file path (default: file_inventory.csv)")
    parser.add_argument("-c", "--chunk-size", type=int, default=10000,
                        help="Number of rows per write chunk (default: 10000)")
    parser.add_argument("-v", "--visualize", action="store_true",
                        help="Generate interactive HTML visualization after scan")
    args = parser.parse_args()

    if not is_root():
        print("Error: This script must be run as root.", file=sys.stderr)
        sys.exit(1)

    csv_path = Path(args.output).resolve()
    chunk_size = args.chunk_size

    print("Scanning local filesystems only (skipping NFS, CIFS, etc.)...")
    local_mounts = get_local_filesystems()
    print(f"Local mount points considered: {sorted(local_mounts)}")

    # Prepare CSV
    fieldnames = ['path', 'size_bytes', 'mtime', 'atime']
    first_write = True
    buffer = []

    count = 0
    start_time = time.time()

    try:
        for record in walk_files_safe(Path('/'), local_mounts):
            buffer.append(record)
            count += 1

            if len(buffer) >= chunk_size:
                mode = 'w' if first_write else 'a'
                with open(csv_path, mode, newline='', encoding='utf-8', errors='replace') as f:
                    writer = csv.writer(f)
                    if first_write:
                        writer.writerow(fieldnames)
                        first_write = False
                    writer.writerows(buffer)
                buffer.clear()
                elapsed = time.time() - start_time
                print(f"Processed {count} files... ({elapsed:.1f}s)", file=sys.stderr)

        # Final flush
        if buffer:
            with open(csv_path, 'a', newline='', encoding='utf-8', errors='replace') as f:
                writer = csv.writer(f)
                writer.writerows(buffer)

        total_time = time.time() - start_time
        print(f"Scan complete: {count} files written to {csv_path} in {total_time:.1f} seconds.")

    except KeyboardInterrupt:
        print("\nInterrupted by user. Partial results saved.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

    # Visualization
    if args.visualize and HAS_VIS:
        try:
            print("Generating visualization...")
            df = pd.read_csv(csv_path, dtype={'path': 'str', 'size_bytes': 'int64'})

            # Convert timestamps to datetime
            df['mtime_dt'] = pd.to_datetime(df['mtime'], unit='s')
            df['atime_dt'] = pd.to_datetime(df['atime'], unit='s')

            # Resample by month for aggregation
            df['mtime_month'] = df['mtime_dt'].dt.to_period('M').dt.start_time
            df['atime_month'] = df['atime_dt'].dt.to_period('M').dt.start_time

            # Aggregate: count and total size per month (for mtime)
            mtime_agg = df.groupby('mtime_month').agg(
                file_count=('path', 'count'),
                total_size=('size_bytes', 'sum')
            ).reset_index()

            # Create plot
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.05,
                subplot_titles=('File Count by Modification Month', 'Total Size by Modification Month')
            )

            # File count
            fig.add_trace(
                go.Bar(x=mtime_agg['mtime_month'], y=mtime_agg['file_count'], name='File Count'),
                row=1, col=1
            )

            # Total size
            fig.add_trace(
                go.Bar(x=mtime_agg['mtime_month'], y=mtime_agg['total_size'], name='Total Size (bytes)'),
                row=2, col=1
            )

            fig.update_layout(
                title="File Inventory by Modification Time (Local Filesystems Only)",
                height=700,
                showlegend=False
            )

            # Add hover with sample file paths (top 10 per month)
            hover_data = {}
            for month in mtime_agg['mtime_month']:
                sample_files = df[df['mtime_month'] == month]['path'].head(10).tolist()
                hover_text = "<br>".join([f"• {p}" for p in sample_files])
                hover_data[month] = f"Files (sample):<br>{hover_text}"

            # Apply hover to both traces
            for trace in fig.data:
                trace.hovertemplate = (
                    '<b>%{x|%Y-%m}</b><br>' +
                    ('File Count: %{y:,}' if 'count' in trace.name else 'Size: %{y:,} bytes') +
                    '<br><br>' +
                    '%{customdata}' +
                    '<extra></extra>'
                )
                trace.customdata = [hover_data.get(x, "") for x in trace.x]

            output_html = csv_path.with_suffix('.html')
            fig.write_html(output_html)
            print(f"Visualization saved to {output_html}")

        except Exception as e:
            print(f"Visualization failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
