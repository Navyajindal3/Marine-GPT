import pyarrow.parquet as pq
from pathlib import Path

# path = Path("data/training/orca_training_2024.parquet")
path = Path("data/training/orca_training_2023.parquet")

pf = pq.ParquetFile(path)

print("=" * 70)
# print("ORCA 2024 DATASET")
print("ORCA 2023 DATASET")
print("=" * 70)

print(f"Rows: {pf.metadata.num_rows:,}")
print(f"Columns: {pf.metadata.num_columns}")
print(f"Row groups: {pf.num_row_groups}")

print("\nSchema:")
for field in pf.schema_arrow:
    print(f"  {field.name}: {field.type}")

print("\nFile size:")
print(f"{path.stat().st_size / (1024**3):.2f} GB")