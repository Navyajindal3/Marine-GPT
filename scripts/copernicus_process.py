import argparse
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path

def process_files(input_dir, output_file):
    three_d_file = input_dir / "glorys_3d.nc"
    surface_file = input_dir / "glorys_surface.nc"

    # Load datasets
    ds_3d = xr.open_dataset(three_d_file)
    ds_surface = xr.open_dataset(surface_file)

    # Remove the single depth dimension
    ds_3d = ds_3d.squeeze("depth", drop=True)

    # Explicitly select the required variables
    ds_3d = ds_3d[["thetao", "uo", "vo", "so"]]
    ds_surface = ds_surface[["zos", "mlotst"]]

    # Merge environmental variables
    ds = xr.merge(
        [ds_3d, ds_surface],
        join="exact"
    )

    # Derived feature: current speed
    ds["current_speed"] = np.sqrt(
        ds["uo"] ** 2 + ds["vo"] ** 2
    )

    # Convert to DataFrame
    df = ds.to_dataframe().reset_index()

    # Rename time -> date
    df = df.rename(columns={"time": "date"})

    # Make sure date is datetime
    df["date"] = pd.to_datetime(df["date"])

    # Select final ORCA environmental feature columns
    columns = [
        "date",
        "latitude",
        "longitude",
        "thetao",
        "uo",
        "vo",
        "so",
        "zos",
        "mlotst",
        "current_speed",
    ]

    df = df[columns]

    df = df.sort_values(
        ["date", "latitude", "longitude"]
    ).reset_index(drop=True)

    # Save
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_parquet(
        output_file,
        index=False
    )

    print("\nProcessed GLORYS data:")
    print(df.to_string(index=False))

    print("\nColumns:")
    print(df.columns.tolist())

    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process Copernicus GLORYS extraction"
    )

    parser.add_argument(
        "--input-dir",
        required=True
    )

    parser.add_argument(
        "--output",
        required=True
    )

    args = parser.parse_args()

    process_files(
        Path(args.input_dir),
        Path(args.output)
    )