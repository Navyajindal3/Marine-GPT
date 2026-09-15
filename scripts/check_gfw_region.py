import pandas as pd

file = "data/gfw_processed/gfw_fishing_effort_2012.parquet"

df = pd.read_parquet(file)

print("Original shape:", df.shape)
print("Date dtype:", df["date"].dtype)

# Spatial filter only
region = df[
    (df["latitude"] >= 15)
    & (df["latitude"] <= 15.2)
    & (df["longitude"] >= 70)
    & (df["longitude"] <= 70.2)
].copy()

print("\nRows in spatial region:", len(region))

print("\nDates found in region:")
print(region["date"].value_counts().sort_index())

print("\nSample rows:")
print(region.head(20).to_string(index=False))