from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import xarray as xr


def load_gfw(gfw_file):
    df = pd.read_parquet(gfw_file)

    df = df[
        (df["latitude"] >= 15)
        & (df["latitude"] <= 15.2)
        & (df["longitude"] >= 70)
        & (df["longitude"] <= 70.2)
    ].copy()

    # GFW coordinates are lower-left cell corners.
    df["cell_lat"] = df["latitude"] + 0.05
    df["cell_lon"] = df["longitude"] + 0.05

    return df


def load_glorys(glorys_file):
    df = pd.read_parquet(glorys_file)

    df = df.rename(
        columns={
            "latitude": "env_lat",
            "longitude": "env_lon",
        }
    )

    return df


def sample_glorys_to_gfw(gfw, glorys):
    features = [
        "thetao",
        "uo",
        "vo",
        "so",
        "zos",
        "mlotst",
        "current_speed",
    ]

    rows = []

    for _, row in gfw.iterrows():

        lat = row["cell_lat"]
        lon = row["cell_lon"]

        distances = (
            (glorys["env_lat"] - lat) ** 2
            + (glorys["env_lon"] - lon) ** 2
        )

        idx = distances.idxmin()

        nearest = glorys.loc[idx]

        output = row.to_dict()

        for feature in features:
            output[feature] = nearest[feature]

        output["glorys_lat"] = nearest["env_lat"]
        output["glorys_lon"] = nearest["env_lon"]

        rows.append(output)

    return pd.DataFrame(rows)


def load_modis(modis_file):
    df = pd.read_parquet(modis_file)

    return df


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--gfw", required=True)
    parser.add_argument("--glorys", required=True)
    parser.add_argument("--modis", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    gfw = load_gfw(Path(args.gfw))

    print(f"GFW rows: {len(gfw)}")

    glorys = load_glorys(Path(args.glorys))

    combined = sample_glorys_to_gfw(gfw, glorys)

    print(f"After GLORYS alignment: {len(combined)}")

    modis = load_modis(Path(args.modis))

    # Match MODIS grid to GFW cell center.
    combined = combined.merge(
        modis,
        left_on=["cell_lat", "cell_lon"],
        right_on=["env_lat", "env_lon"],
        how="left",
    )

    # Remove duplicate environmental coordinate columns.
    combined = combined.drop(
        columns=["env_lat", "env_lon"],
        errors="ignore",
    )

    combined["date"] = pd.to_datetime(combined["date"])

    combined["month"] = combined["date"].dt.month

    # Cyclic seasonal representation.
    combined["month_sin"] = np.sin(
        2 * np.pi * combined["month"] / 12
    )

    combined["month_cos"] = np.cos(
        2 * np.pi * combined["month"] / 12
    )

    combined = combined.sort_values(
        ["date", "latitude", "longitude"]
    ).reset_index(drop=True)

    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    combined.to_parquet(output_file, index=False)

    print("\nFinal multimodal test table:")
    print(combined.to_string(index=False))

    print("\nColumns:")
    print(combined.columns.tolist())

    print("\nMissing values:")
    print(combined.isna().sum())

    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    main()

    python scripts\build_training_test.py `
  --gfw data\gfw_processed\gfw_fishing_effort_2012.parquet `
  --glorys data\copernicus_grid_test\glorys_processed.parquet `
  --modis data\alignment_test\modis_chlorophyll.parquet `
  --output data\alignment_test\orca_multimodal_test.parquet