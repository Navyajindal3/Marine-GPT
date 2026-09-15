import pandas as pd

files = [
    "data/copernicus_grid_test/glorys_processed.parquet",
    "data/copernicus_test_script/glorys_processed.parquet",
]

for file in files:
    df = pd.read_parquet(file)

    print("\nFILE:", file)
    print("Rows:", len(df))
    print("Date:", df["date"].min(), "->", df["date"].max())
    print("Latitude:", df["latitude"].min(), "->", df["latitude"].max())
    print("Longitude:", df["longitude"].min(), "->", df["longitude"].max())