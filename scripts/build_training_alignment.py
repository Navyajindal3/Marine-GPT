from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import xarray as xr


def load_glorys(glorys_file):
    df = pd.read_parquet(glorys_file)

    df["date"] = pd.to_datetime(df["date"])

    required = [
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

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"Missing GLORYS columns: {missing}")

    return df[required].copy()


def load_modis(modis_file):
    ds = xr.open_dataset(modis_file)

    chlorophyll = ds["chlor_a"]

    return chlorophyll


def load_gfw(gfw_file, target_date, lat_min, lat_max, lon_min, lon_max):
    df = pd.read_parquet(gfw_file)

    df["date"] = pd.to_datetime(df["date"])

    target_date = pd.Timestamp(target_date)

    df = df[
        (df["date"] == target_date)
        & (df["latitude"] >= lat_min)
        & (df["latitude"] <= lat_max)
        & (df["longitude"] >= lon_min)
        & (df["longitude"] <= lon_max)
    ].copy()

    required = [
        "date",
        "latitude",
        "longitude",
        "fishing_hours",
        "total_hours",
        "active_fishing",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"Missing GFW columns: {missing}")

    return df[required].copy()


def assign_gfw_to_glorys(gfw, glorys):
    """
    Assign each GFW 0.01-degree observation to its nearest
    GLORYS environmental grid cell.

    GFW fishing_hours are then aggregated by the GLORYS cell.
    """

    target_lat = np.sort(glorys["latitude"].unique())
    target_lon = np.sort(glorys["longitude"].unique())

    gfw_lat = gfw["latitude"].to_numpy()
    gfw_lon = gfw["longitude"].to_numpy()

    lat_idx = np.abs(
        gfw_lat[:, None] - target_lat[None, :]
    ).argmin(axis=1)

    lon_idx = np.abs(
        gfw_lon[:, None] - target_lon[None, :]
    ).argmin(axis=1)

    gfw = gfw.copy()

    gfw["latitude"] = target_lat[lat_idx]
    gfw["longitude"] = target_lon[lon_idx]

    aggregated = (
        gfw.groupby(
            ["date", "latitude", "longitude"],
            as_index=False
        )
        .agg(
            fishing_hours=("fishing_hours", "sum"),
            total_hours=("total_hours", "sum"),
            active_fishing=("active_fishing", "max"),
        )
    )

    return aggregated


def extract_modis_for_grid(modis, glorys):
    """
    Extract nearest MODIS chlorophyll value for every GLORYS cell.
    """

    lat_values = xr.DataArray(
        glorys["latitude"].to_numpy(),
        dims="points"
    )

    lon_values = xr.DataArray(
        glorys["longitude"].to_numpy(),
        dims="points"
    )

    values = modis.sel(
        lat=lat_values,
        lon=lon_values,
        method="nearest"
    ).to_numpy()

    result = glorys[
        ["latitude", "longitude"]
    ].copy()

    result["chlorophyll"] = values

    result["chlorophyll_missing"] = (
        result["chlorophyll"].isna().astype("int8")
    )

    return result


def build_alignment(
    gfw_file,
    glorys_file,
    modis_file,
    output_file,
    target_date,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
):
    print("\nLoading GFW...")
    gfw = load_gfw(
        gfw_file,
        target_date,
        lat_min,
        lat_max,
        lon_min,
        lon_max,
    )

    print(f"GFW rows: {len(gfw):,}")

    print("\nLoading GLORYS...")
    glorys = load_glorys(glorys_file)

    glorys = glorys[
        (glorys["date"] == pd.Timestamp(target_date))
        & (glorys["latitude"] >= lat_min)
        & (glorys["latitude"] <= lat_max)
        & (glorys["longitude"] >= lon_min)
        & (glorys["longitude"] <= lon_max)
    ].copy()

    print(f"GLORYS rows: {len(glorys):,}")

    print("\nAggregating GFW onto GLORYS grid...")

    gfw_agg = assign_gfw_to_glorys(
        gfw,
        glorys
    )

    print(
        f"Aggregated GFW rows: "
        f"{len(gfw_agg):,}"
    )

    print("\nLoading MODIS...")
    modis = load_modis(modis_file)

    print("\nExtracting MODIS onto GLORYS grid...")

    modis_grid = extract_modis_for_grid(
        modis,
        glorys
    )

    modis_grid["date"] = pd.Timestamp(target_date)

    print("\nCombining datasets...")

    result = glorys.merge(
        gfw_agg,
        on=["date", "latitude", "longitude"],
        how="left"
    )

    result = result.merge(
        modis_grid[
            [
                "date",
                "latitude",
                "longitude",
                "chlorophyll",
                "chlorophyll_missing",
            ]
        ],
        on=["date", "latitude", "longitude"],
        how="left"
    )

    # A GLORYS grid cell with no GFW record means
    # no GFW activity was reported for that cell.
    result["fishing_hours"] = (
        result["fishing_hours"].fillna(0)
    )

    result["total_hours"] = (
        result["total_hours"].fillna(0)
    )

    result["active_fishing"] = (
        result["active_fishing"].fillna(0)
        .astype("int8")
    )

    result["fishing_hours"] = result[
        "fishing_hours"
    ].astype("float32")

    result["total_hours"] = result[
        "total_hours"
    ].astype("float32")

    result["current_speed"] = np.sqrt(
        result["uo"] ** 2 +
        result["vo"] ** 2
    )

    result = result.sort_values(
        ["date", "latitude", "longitude"]
    ).reset_index(drop=True)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result.to_parquet(
        output_file,
        index=False
    )

    print("\n==============================")
    print("FINAL ALIGNMENT")
    print("==============================")

    print(
        f"Shape: {result.shape}"
    )

    print(
        f"Date: "
        f"{result['date'].min()} → "
        f"{result['date'].max()}"
    )

    print(
        f"Latitude: "
        f"{result['latitude'].min()} → "
        f"{result['latitude'].max()}"
    )

    print(
        f"Longitude: "
        f"{result['longitude'].min()} → "
        f"{result['longitude'].max()}"
    )

    print(
        f"Fishing hours: "
        f"{result['fishing_hours'].sum():.4f}"
    )

    print(
        f"Active cells: "
        f"{result['active_fishing'].sum():,}"
    )

    print(
        f"Chlorophyll valid: "
        f"{result['chlorophyll'].notna().sum():,}"
    )

    print(
        f"Chlorophyll missing: "
        f"{result['chlorophyll'].isna().sum():,}"
    )

    print("\nColumns:")
    print(result.columns.tolist())

    print(
        f"\nSaved to: {output_file}"
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Build ORCA canonical-grid training alignment"
    )

    parser.add_argument(
        "--gfw",
        required=True
    )

    parser.add_argument(
        "--glorys",
        required=True
    )

    parser.add_argument(
        "--modis",
        required=True
    )

    parser.add_argument(
        "--output",
        required=True
    )

    parser.add_argument(
        "--date",
        required=True
    )

    parser.add_argument(
        "--lat-min",
        type=float,
        required=True
    )

    parser.add_argument(
        "--lat-max",
        type=float,
        required=True
    )

    parser.add_argument(
        "--lon-min",
        type=float,
        required=True
    )

    parser.add_argument(
        "--lon-max",
        type=float,
        required=True
    )

    args = parser.parse_args()

    build_alignment(
        Path(args.gfw),
        Path(args.glorys),
        Path(args.modis),
        Path(args.output),
        args.date,
        args.lat_min,
        args.lat_max,
        args.lon_min,
        args.lon_max,
    )