import pandas as pd
import matplotlib.pyplot as plt
import glob
import os

def readable_size(num):
    """Convert number to human readable format with B, KB, MB units"""
    if abs(num) < 1024:
        return f"{num:.0f} B"
    elif abs(num) < 1024**2:
        return f"{num/1024:.2f} KB"
    else:
        return f"{num/(1024**2):.2f} MB"

def percent_format(num):
    """Format number as percent with 2 decimals"""
    return f"{num:.2f}%"

def plot_stacked_bar_with_table(df, mode):
    # Sort descending by abs(delta_total) and take top 15
    df = df.reindex(df['delta_total'].abs().sort_values(ascending=False).index)
    df_top = df.head(15).reset_index(drop=True)
    df_top['group'] = df_top['group'].astype(str)

    fig, ax = plt.subplots(figsize=(12, 6))

    # Prepare the data for stacked bar: old_total and difference parts
    # For better visualization, stack old_total and added delta_total separately by their sign
    old_vals = df_top['old_total']
    delta_vals = df_top['delta_total']

    # Bars: old_total base + positive part of delta, negative part separately
    ax.barh(df_top['group'], old_vals, color='lightgray', label='Old Size')

    # For positive delta, add on top of old_total
    pos_delta = delta_vals.clip(lower=0)
    ax.barh(df_top['group'], pos_delta, 
            left=old_vals, color='steelblue', label='Increase (Diff)')

    # For negative delta, plot separately to the left of old_total
    neg_delta = delta_vals.clip(upper=0)
    ax.barh(df_top['group'], neg_delta, 
            left=old_vals, color='indianred', label='Decrease (Diff)')

    ax.set_xlabel('Size')
    ax.set_title(f'Stacked Size with Diff by Group - {mode}')
    ax.invert_yaxis()

    # Label the total (old_total + delta_total) to the right end of each bar
    total_vals = old_vals + delta_vals
    for i, (oldv, deltav, totalv) in enumerate(zip(old_vals, delta_vals, total_vals)):
        ax.text(totalv if totalv > 0 else totalv, i,
                readable_size(totalv),
                va='center',
                ha='left' if totalv >= 0 else 'right',
                fontsize=9,
                color='black')

    # Prepare table data with readable sizes
    cell_text = []
    for _, row in df_top.iterrows():
        cell_text.append([
            row['group'],
            readable_size(row['old_total']),
            readable_size(row['new_total']),
            readable_size(row['delta_total']),
            percent_format(row['delta_pct'])
        ])

    # Adjust plot to make room for table (on right)
    box = ax.get_position()
    fig.subplots_adjust(right=0.7)

    # New axis for table
    table_ax = fig.add_axes([0.72, box.y0, 0.28, box.height])
    table_ax.axis('off')

    # Create table
    table = table_ax.table(cellText=cell_text,
                           colLabels=['Group', 'Old Size', 'New Size', 'Diff', 'Diff %'],
                           cellLoc='center',
                           loc='center')

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)

    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
    filename = f'stacked_chart_{mode}.png'
    plt.savefig(filename, dpi=200, bbox_inches='tight')
    plt.close(fig)
    return filename

# Process all CSV files in current directory
csv_files = glob.glob('*.csv')
saved_files = []

for fname in csv_files:
    df = pd.read_csv(fname)
    df['group'] = df['group'].astype(str)
    mode = df['mode'][0] if 'mode' in df.columns else os.path.splitext(fname)[0]
    filename = plot_stacked_bar_with_table(df[['group', 'old_total', 'new_total', 'delta_total', 'delta_pct']], mode)
    saved_files.append(filename)

print("Saved stacked bar chart files:", saved_files)
