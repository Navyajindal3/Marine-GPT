from pathlib import Path
import pandas as pd

input_dir = Path("data/training/2023")
output_file = Path("data/training/orca_training_2023.parquet")

files = sorted(input_dir.glob("orca_training_2023_*.parquet"))

print(f"Found {len(files)} monthly files")

if len(files) != 12:
    raise RuntimeError(
        f"Expected 12 monthly files, found {len(files)}"
    )

dfs = []

for file in files:
    print(f"Loading {file.name}")
    df = pd.read_parquet(file)
    print(f"  Rows: {len(df):,}")
    dfs.append(df)

combined = pd.concat(dfs, ignore_index=True)

combined.to_parquet(
    output_file,
    index=False,
    compression="snappy"
)

print("\n" + "=" * 70)
print("✓ FINAL 2023 DATASET CREATED")
print("=" * 70)
print(f"Rows: {len(combined):,}")
print(f"Columns: {len(combined.columns)}")
print(f"Output: {output_file}")
print("\nColumns:")
print(list(combined.columns))