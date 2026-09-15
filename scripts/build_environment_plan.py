from pathlib import Path
import argparse
import pandas as pd
import numpy as np


def nearest_index(values, targets):
    """
    Find the nearest target coordinate for every source coordinate.

    Both arrays must be sorted.
    """

    values = np.asarray(values)
    targets = np.asarray(targets)

    idx = np.searchsorted(targets, values)

    idx = np.clip(idx, 1, len(targets) - 1)

    left = targets[idx - 1]
    right = targets[idx]

    choose_right = (
        np.abs(values - right)
        < np.abs(values - left)
    )

    idx -= (~choose_right)

    return idx


def build_plan(
    gfw_file,
    output_file,
    lat_min=-90,
    lat_max=90,
    lon_min=-180,
    lon_max=180,
):

    print("Loading GFW...")

    gfw = pd.read_parquet(gfw_file)

    required = [
        "date",
        "latitude",
        "longitude",
        "fishing_hours",
        "total_hours",
        "active_fishing",
    ]

    missing = [
        column
        for column in required
        if column not in gfw.columns
    ]

    if missing:
        raise ValueError(
            f"Missing GFW columns: {missing}\n"
            f"Available columns: {gfw.columns.tolist()}"
        )

    gfw["date"] = pd.to_datetime(gfw["date"])

    gfw = gfw[
        gfw["latitude"].between(
            lat_min,
            lat_max
        )
        &
        gfw["longitude"].between(
            lon_min,
            lon_max
        )
    ].copy()

    print(f"GFW rows: {len(gfw):,}")

    # ---------------------------------------------------------
    # Canonical environmental grid
    #
    # GLORYS global grid is approximately 1/12 degree.
    # We use the theoretical grid only for planning.
    #
    # Actual Copernicus coordinates will be used during
    # environmental extraction.
    # ---------------------------------------------------------

    resolution = 1 / 12

    glorys_lat = np.arange(
        -90,
        90 + resolution / 2,
        resolution
    )

    glorys_lon = np.arange(
        -180,
        180 + resolution / 2,
        resolution
    )

    print(
        f"Potential GLORYS latitude coordinates: "
        f"{len(glorys_lat):,}"
    )

    print(
        f"Potential GLORYS longitude coordinates: "
        f"{len(glorys_lon):,}"
    )

    # ---------------------------------------------------------
    # Map GFW coordinates to nearest GLORYS coordinate
    # ---------------------------------------------------------

    print("\nMapping GFW cells to canonical grid...")

    lat_idx = nearest_index(
        gfw["latitude"].to_numpy(),
        glorys_lat
    )

    lon_idx = nearest_index(
        gfw["longitude"].to_numpy(),
        glorys_lon
    )

    gfw["canonical_latitude"] = (
        glorys_lat[lat_idx]
    )

    gfw["canonical_longitude"] = (
        glorys_lon[lon_idx]
    )

    # ---------------------------------------------------------
    # Unique date + canonical cell combinations
    # ---------------------------------------------------------

    plan = (
        gfw[
            [
                "date",
                "canonical_latitude",
                "canonical_longitude",
            ]
        ]
        .drop_duplicates()
        .rename(
            columns={
                "canonical_latitude": "latitude",
                "canonical_longitude": "longitude",
            }
        )
        .sort_values(
            [
                "date",
                "latitude",
                "longitude",
            ]
        )
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # Daily extraction summary
    # ---------------------------------------------------------

    daily = (
        plan.groupby("date")
        .agg(
            lat_min=("latitude", "min"),
            lat_max=("latitude", "max"),
            lon_min=("longitude", "min"),
            lon_max=("longitude", "max"),
            grid_cells=("latitude", "size"),
        )
        .reset_index()
    )

    # ---------------------------------------------------------
    # Spatial summary
    # ---------------------------------------------------------

    spatial = (
        plan[
            [
                "latitude",
                "longitude",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "latitude",
                "longitude",
            ]
        )
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # Save outputs
    # ---------------------------------------------------------

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    plan_file = output_file.with_name(
        output_file.stem + "_cells.parquet"
    )

    daily_file = output_file.with_name(
        output_file.stem + "_daily.parquet"
    )

    spatial_file = output_file.with_name(
        output_file.stem + "_spatial.parquet"
    )

    plan.to_parquet(
        plan_file,
        index=False
    )

    daily.to_parquet(
        daily_file,
        index=False
    )

    spatial.to_parquet(
        spatial_file,
        index=False
    )

    # ---------------------------------------------------------
    # Report
    # ---------------------------------------------------------

    print("\n==============================")
    print("ENVIRONMENT EXTRACTION PLAN")
    print("==============================")

    print(
        f"Unique date/grid cells: "
        f"{len(plan):,}"
    )

    print(
        f"Unique dates: "
        f"{plan['date'].nunique():,}"
    )

    print(
        f"Unique spatial cells: "
        f"{len(spatial):,}"
    )

    print(
        f"Latitude range: "
        f"{plan['latitude'].min():.4f} → "
        f"{plan['latitude'].max():.4f}"
    )

    print(
        f"Longitude range: "
        f"{plan['longitude'].min():.4f} → "
        f"{plan['longitude'].max():.4f}"
    )

    print("\nFirst daily records:")

    print(
        daily.head(10).to_string(
            index=False
        )
    )

    print("\nFirst spatial cells:")

    print(
        spatial.head(10).to_string(
            index=False
        )
    )

    print("\nSaved:")

    print(plan_file)
    print(daily_file)
    print(spatial_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Build ORCA environmental extraction plan "
            "from processed GFW data"
        )
    )

    parser.add_argument(
        "--gfw",
        required=True
    )

    parser.add_argument(
        "--output",
        required=True
    )

    parser.add_argument(
        "--lat-min",
        type=float,
        default=-90
    )

    parser.add_argument(
        "--lat-max",
        type=float,
        default=90
    )

    parser.add_argument(
        "--lon-min",
        type=float,
        default=-180
    )

    parser.add_argument(
        "--lon-max",
        type=float,
        default=180
    )

    args = parser.parse_args()

    build_plan(
        Path(args.gfw),
        Path(args.output),
        args.lat_min,
        args.lat_max,
        args.lon_min,
        args.lon_max,
    )