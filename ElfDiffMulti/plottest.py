import pandas as pd
import matplotlib.pyplot as plt
import glob
import os

# 1. 불러올 csv 파일 목록
csv_files = glob.glob('*.csv')  # 같은 폴더 내 모든 csv

data_list = []
modes = []

# 2. 각 파일을 읽어들여 DataFrame에 저장
for fname in csv_files:
    df = pd.read_csv(fname, sep=',')
    mode = df['mode'].iloc[0] if 'mode' in df.columns else os.path.splitext(fname)[0]
    data_list.append(df[['group', 'delta_total']].set_index('group'))
    modes.append(mode)

# 3. 그룹 기준으로 데이터 병합
merged = pd.concat(data_list, axis=1, keys=modes)
merged.columns = merged.columns.droplevel(1)  # 컬럼 다듬기
merged = merged.fillna(0)  # 없는 값은 0으로

# 4. 차트 그리기
fig, ax = plt.subplots(figsize=(14,7))

bar_width = 0.35
index = range(len(merged))

for i, mode in enumerate(modes):
    ax.bar(
        [x + bar_width*i for x in index],
        merged[mode],
        width=bar_width,
        label=mode,
        alpha=0.8
    )

ax.set_xticks([x + bar_width*(len(modes)-1)/2 for x in index])
ax.set_xticklabels(merged.index, rotation=45, ha='right')
ax.set_ylabel('Delta Total')
ax.set_xlabel('Group')
ax.set_title('Group-wise Delta Total Comparison by Mode')
ax.legend(title='Mode')
plt.tight_layout()
plt.savefig('multi_bar_chart.png', dpi=200)
plt.show()
