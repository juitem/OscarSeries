import pandas as pd
import argparse

def compare_csv_files(csv1, csv2, output_csv): 
df1 = pd.read_csv(csv1) 
df2 = pd.read_csv(csv2) 

# Unify UniqID column type as string 
df1['UniqID'] = df1['UniqID'].astype(str) 
df2['UniqID'] = df2['UniqID'].astype(str) 

total_size_1 = df1['filesize'].sum() 
total_size_2 = df2['filesize'].sum() 

merged = pd.merge(df1, df2, on='UniqID', how='outer', 
suffixes=('_1', '_2'), indicator=True) 

only_in_1 = merged[merged['_merge'] == 'left_only']['filesize_1'].sum() 
only_in_2 = merged[merged['_merge'] == 'right_only']['filesize_2'].sum() 

both = merged[merged['_merge'] == 'both'].copy() 
both['size_diff'] = both['filesize_1'] - both['filesize_2'] 
same_files_total_diff = both['size_diff'].sum() 

summary = [ 
['Total Size Folder 1', total_size_1], 
['Total Size Folder 2', total_size_2], 
['Only in Folder 1', only_in_1], 
['Only in Folder 2', only_in_2], 
['Total Size Difference (Folder1 - Folder2)', total_size_1 - total_size_2], 
['Sum of Size Difference for Same Files', same_files_total_diff] 
] 
summary_df = pd.DataFrame(summary, columns=['Category', 'Size']) 

print('\n=== Folder Comparison Summary ===') 
print(summary_df.to_string(index=False)) 

merged.to_csv(output_csv, index=False) 
summary_df.to_csv('summary_' + output_csv, index=False)

if __name__ == "__main__": 
parser = argparse.ArgumentParser(description='Folder CSV Comparison Tool')
parser.add_argument('csv1', help='First CSV file path')
parser.add_argument('csv2', help='Second CSV file path')
parser.add_argument('output_csv', help='Result save CSV file name')
args = parser.parse_args()

compare_csv_files(args.csv1, args.csv2, args.output_csv)
print(f"\nResult save complete: {args.output_csv}")
