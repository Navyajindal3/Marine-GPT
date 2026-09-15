import pandas as pd

files = {
    "GFW": "data/gfw_processed/gfw_fishing_effort_2012.parquet",
    "GLORYS": "data/alignment_test/glorys_processed.parquet",
    "MODIS": "data/alignment_test/modis_chlorophyll.parquet",
}

for name, path in files.items():
    df = pd.read_parquet(path)

    print("\n" + "=" * 60)
    print(name)
    print("=" * 60)

    print("Shape:", df.shape)
    print("Columns:", df.columns.tolist())

    if "date" in df.columns:
        print("Date:", df["date"].min(), "->", df["date"].max())

    for col in ["latitude", "longitude", "cell_lat", "cell_lon",
                "env_lat", "env_lon"]:
        if col in df.columns:
            print(
                f"{col}:",
                df[col].min(),
                "->",
                df[col].max()
            )

    print("\nFirst 5 rows:")
    print(df.head())