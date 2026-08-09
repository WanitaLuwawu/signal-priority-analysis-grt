import pandas as pd

df = pd.read_csv("outputs/tsp_candidate_rankings.csv")
delays = pd.read_csv("data/realtime/delay_records.csv")

print("Priority tier counts:")
print(df["tsp_priority"].value_counts())
print(f"Total signals ranked: {len(df)}")
print(f"\nDelay records collected: {len(delays):,}")
print(f"Snapshots collected: {delays['snapshot_time'].nunique()}")
print(f"Date range: {delays['snapshot_time'].min()} → {delays['snapshot_time'].max()}")
print(f"\nAvg delay across all records: {delays['delay_sec'].mean():.1f} sec")
print(f"Stops with delay data: {delays['stop_id'].nunique()}")