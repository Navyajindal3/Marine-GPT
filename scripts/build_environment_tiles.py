from pathlib import Path
import argparse
import numpy as np
import pandas as pd


TILE_SIZE = 5.0


def floor_tile(value):
    return np.floor(value / TILE_SIZE) * TILE_SIZE


def build_tiles(cells_file, output_file):

    print("Loading exact environment plan...")

    cells = pd.read_parquet(cells_file)

    required = [
        "date",
        "latitude",
        "longitude",
    ]

    missing = [
        c for c in required
        if c not in cells.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}\n"
            f"Available: {cells.columns.tolist()}"
        )

    # ---------------------------------------------------------
    # Assign each GLORYS cell to a 5° × 5° tile
    # ---------------------------------------------------------

    cells["tile_lat_min"] = (
        cells["latitude"]
        .apply(floor_tile)
    )

    cells["tile_lon_min"] = (
        cells["longitude"]
        .apply(floor_tile)
    )

    cells["tile_lat_max"] = (
        cells["tile_lat_min"] + TILE_SIZE
    )

    cells["tile_lon_max"] = (
        cells["tile_lon_min"] + TILE_SIZE
    )

    # ---------------------------------------------------------
    # Unique spatial tiles
    # ---------------------------------------------------------

    tiles = (
        cells[
            [
                "tile_lat_min",
                "tile_lat_max",
                "tile_lon_min",
                "tile_lon_max",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "tile_lat_min",
                "tile_lon_min",
            ]
        )
        .reset_index(drop=True)
    )

    tiles.insert(
        0,
        "tile_id",
        [
            f"T{i:05d}"
            for i in range(len(tiles))
        ]
    )

    # ---------------------------------------------------------
    # Spatial statistics
    # ---------------------------------------------------------

    spatial_stats = (
        cells
        .groupby(
            [
                "tile_lat_min",
                "tile_lon_min",
            ]
        )
        .agg(
            spatial_cells=(
                "latitude",
                "size",
            ),

            unique_dates=(
                "date",
                "nunique",
            ),

            date_cell_observations=(
                "date",
                "size",
            ),
        )
        .reset_index()
    )

    tiles = tiles.merge(
        spatial_stats,
        on=[
            "tile_lat_min",
            "tile_lon_min",
        ],
        how="left",
    )

    # ---------------------------------------------------------
    # Date ranges
    # ---------------------------------------------------------

    date_stats = (
        cells
        .groupby(
            [
                "tile_lat_min",
                "tile_lon_min",
            ]
        )
        .agg(
            start_date=("date", "min"),
            end_date=("date", "max"),
        )
        .reset_index()
    )

    tiles = tiles.merge(
        date_stats,
        on=[
            "tile_lat_min",
            "tile_lon_min",
        ],
        how="left",
    )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    tiles.to_parquet(
        output_file,
        index=False
    )

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    print("\n==============================")
    print("ENVIRONMENT TILE PLAN")
    print("==============================")

    print(
        f"Tile size: {TILE_SIZE}° × {TILE_SIZE}°"
    )

    print(
        f"Total tiles: {len(tiles):,}"
    )

    print(
        f"Total spatial cells: "
        f"{tiles['spatial_cells'].sum():,}"
    )

    print(
        f"Total date/cell observations: "
        f"{tiles['date_cell_observations'].sum():,}"
    )

    print("\nSpatial cells per tile:")

    print(
        tiles["spatial_cells"]
        .describe()
        .to_string()
    )

    print("\nDate/cell observations per tile:")

    print(
        tiles["date_cell_observations"]
        .describe()
        .to_string()
    )

    print("\nLargest tiles:")

    print(
        tiles
        .sort_values(
            "date_cell_observations",
            ascending=False,
        )
        .head(10)
        .to_string(index=False)
    )

    print("\nSaved:")
    print(output_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--cells",
        required=True
    )

    parser.add_argument(
        "--output",
        required=True
    )

    args = parser.parse_args()

    build_tiles(
        Path(args.cells),
        Path(args.output),
    )