
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