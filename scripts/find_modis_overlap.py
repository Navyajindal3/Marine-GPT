from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

GFW_FILE = Path("data/gfw_processed/gfw_fishing_effort_2012.parquet")

MODIS_FILE = Path(
    "data/alignment_test/modis/"
    "AQUA_MODIS.20120327.L3m.DAY.CHL.chlor_a.9km.nc"
)

gfw = pd.read_parquet(GFW_FILE)
gfw = gfw[gfw["date"] == "2012-03-27"].copy()

ds = xr.open_dataset(MODIS_FILE)
chlorophyll = ds["chlor_a"]

valid = []

for _, row in gfw.iterrows():
    value = chlorophyll.sel(
        lat=row["latitude"],
        lon=row["longitude"],
        method="nearest"
    ).values

    if np.isfinite(value):
        valid.append(row)

valid = pd.DataFrame(valid)

print(f"Total GFW cells: {len(gfw)}")
print(f"Valid MODIS cells: {len(valid)}")

if len(valid) > 0:
    print("\nValid MODIS/GFW extent:")
    print(f"Latitude:  {valid.latitude.min():.2f} to {valid.latitude.max():.2f}")
    print(f"Longitude: {valid.longitude.min():.2f} to {valid.longitude.max():.2f}")

    # Find the densest 0.5° × 0.5° area
    valid["lat_bin"] = np.floor(valid["latitude"] * 2) / 2
    valid["lon_bin"] = np.floor(valid["longitude"] * 2) / 2

    clusters = (
        valid.groupby(["lat_bin", "lon_bin"])
        .size()
        .sort_values(ascending=False)
    )

    print("\nTop 5 compact regions:")
    print(clusters.head(5).to_string())