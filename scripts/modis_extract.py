from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import xarray as xr


def load_gfw_grid(gfw_file):
    df = pd.read_parquet(gfw_file)

    df = df[
        (df["date"] == pd.Timestamp("2012-03-27"))
        & (df["latitude"] >= 15)
        & (df["latitude"] <= 15.2)
        & (df["longitude"] >= 70)
        & (df["longitude"] <= 70.2)
    ].copy()

    # GFW coordinates are lower-left corners of 0.1° cells.
    # Represent each cell by its center.
    df["cell_lat"] = df["latitude"] + 0.05
    df["cell_lon"] = df["longitude"] + 0.05

    # Only need unique cells for the environmental extraction.
    grid = df[
        ["latitude", "longitude", "cell_lat", "cell_lon"]
    ].drop_duplicates()

    return grid


def extract_chlorophyll(modis_file, gfw_grid):
    ds = xr.open_dataset(modis_file)

    chlor = ds["chlor_a"]

    print("\nMODIS coordinates:")
    print("Latitude:", float(chlor.lat.min()), "->", float(chlor.lat.max()))
    print("Longitude:", float(chlor.lon.min()), "->", float(chlor.lon.max()))

    rows = []

    for _, row in gfw_grid.iterrows():

        target_lat = row["cell_lat"]
        target_lon = row["cell_lon"]

        # Nearest MODIS pixel
        value = chlor.sel(
            lat=target_lat,
            lon=target_lon,
            method="nearest",
        ).item()

        rows.append(
            {
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "cell_lat": target_lat,
                "cell_lon": target_lon,
                "chlorophyll": value,
            }
        )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Extract MODIS chlorophyll onto the GFW 0.1° grid"
    )

    parser.add_argument("--gfw", required=True)
    parser.add_argument("--modis", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    gfw_file = Path(args.gfw)
    modis_file = Path(args.modis)
    output_file = Path(args.output)

    gfw_grid = load_gfw_grid(gfw_file)

    print("GFW cells:")
    print(gfw_grid.to_string(index=False))

    modis_df = extract_chlorophyll(
        modis_file,
        gfw_grid,
    )

    print("\nExtracted MODIS values:")
    print(modis_df.to_string(index=False))

    print("\nMissing chlorophyll:")
    print(modis_df["chlorophyll"].isna().sum())

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    modis_df.to_parquet(
        output_file,
        index=False,
    )

    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    main()