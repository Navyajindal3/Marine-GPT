from pathlib import Path
import argparse
import calendar
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import xarray as xr


# ============================================================
# CONFIG
# ============================================================

GLORYS_DATASET = "cmems_mod_glo_phy_my_0.083deg_P1D-m"

# Download container size only.
# It does NOT change the final spatial resolution.
TILE_SIZE = 40.0

# Keep this conservative so the laptop does not run out of RAM.
MAX_WORKERS = 2

GRID_PADDING = 0.08334

GRID_LAT_MIN = -80.0
GRID_LAT_MAX = 85.0

GRID_LON_MIN = -180.0
GRID_LON_MAX = 179.9166717529297


# ============================================================
# NEAREST GRID INDEX
# ============================================================

def nearest_indices(values, grid):
    """
    Return nearest index in sorted grid for every value.
    """

    values = np.asarray(values, dtype=np.float64)
    grid = np.asarray(grid, dtype=np.float64)

    idx = np.searchsorted(grid, values)

    idx = np.clip(
        idx,
        1,
        len(grid) - 1,
    )

    left = grid[idx - 1]
    right = grid[idx]

    choose_right = (
        np.abs(values - right)
        <
        np.abs(values - left)
    )

    idx = idx - (~choose_right)

    return idx.astype(np.int64)


# ============================================================
# LOAD CANONICAL GLORYS GRID
# ============================================================

def load_glorys_grid(grid_file):

    print()
    print("=" * 70)
    print("LOADING CANONICAL GLORYS GRID")
    print("=" * 70)

    ds = xr.open_dataset(
        grid_file
    )

    try:
        lat = ds["latitude"].values
        lon = ds["longitude"].values
    finally:
        ds.close()

    lat = np.asarray(
        lat,
        dtype=np.float64,
    )

    lon = np.asarray(
        lon,
        dtype=np.float64,
    )

    print(
        f"Latitude : {len(lat):,} points"
    )

    print(
        f"Longitude: {len(lon):,} points"
    )

    return lat, lon


# ============================================================
# LOAD ONLY ONE MONTH OF GFW
# ============================================================

def load_gfw_month(
    gfw_file,
    year,
    month,
):

    start = pd.Timestamp(
        year=year,
        month=month,
        day=1,
    )

    end = pd.Timestamp(
        year=year,
        month=month,
        day=calendar.monthrange(
            year,
            month,
        )[1],
    )

    print()
    print("=" * 70)
    print(
        f"LOADING GFW {year}-{month:02d}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Read only the columns we need.
    # --------------------------------------------------------

    df = pd.read_parquet(
        gfw_file,
        columns=[
            "date",
            "latitude",
            "longitude",
            "fishing_hours",
            "total_hours",
            "active_fishing",
        ],
        filters=[
            [
                (
                    "date",
                    ">=",
                    start,
                ),
                (
                    "date",
                    "<=",
                    end,
                ),
            ]
        ],
    )

    if df.empty:

        print(
            "No GFW data for this month."
        )

        return df

    df["date"] = pd.to_datetime(
        df["date"]
    ).dt.normalize()

    print(
        f"GFW rows loaded: "
        f"{len(df):,}"
    )

    return df


# ============================================================
# ALIGN ONE MONTH OF GFW
# ============================================================

def align_gfw_to_glorys(
    gfw,
    glorys_lat,
    glorys_lon,
):

    print(
        "Aligning GFW cells to GLORYS grid..."
    )

    # --------------------------------------------------------
    # Map GFW coordinates to nearest actual GLORYS coordinate.
    # --------------------------------------------------------

    lat_idx = nearest_indices(
        gfw["latitude"].to_numpy(),
        glorys_lat,
    )

    lon_idx = nearest_indices(
        gfw["longitude"].to_numpy(),
        glorys_lon,
    )

    gfw = gfw.copy()

    gfw["latitude"] = glorys_lat[
        lat_idx
    ]

    gfw["longitude"] = glorys_lon[
        lon_idx
    ]

    # --------------------------------------------------------
    # Aggregate only THIS MONTH.
    # --------------------------------------------------------

    gfw = (
        gfw
        .groupby(
            [
                "date",
                "latitude",
                "longitude",
            ],
            sort=False,
            as_index=False,
        )
        .agg(
            fishing_hours=(
                "fishing_hours",
                "sum",
            ),
            total_hours=(
                "total_hours",
                "sum",
            ),
            active_fishing=(
                "active_fishing",
                "max",
            ),
        )
    )

    print(
        f"Aligned rows: {len(gfw):,}"
    )

    return gfw


# ============================================================
# ASSIGN DOWNLOAD TILES
# ============================================================

def assign_tiles(df):

    df = df.copy()

    df["tile_lat"] = (
        np.floor(
            df["latitude"] / TILE_SIZE
        )
        * TILE_SIZE
    )

    df["tile_lon"] = (
        np.floor(
            df["longitude"] / TILE_SIZE
        )
        * TILE_SIZE
    )

    return df


# ============================================================
# DOWNLOAD GLORYS TILE
# ============================================================

def download_glorys(
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    start_date,
    end_date,
    output_file,
):

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "copernicusmarine",
        "subset",

        "-i",
        GLORYS_DATASET,

        # ----------------------------------------------------
        # ALL SIX ENVIRONMENTAL VARIABLES
        # ----------------------------------------------------

        "-v",
        "thetao",

        "-v",
        "uo",

        "-v",
        "vo",

        "-v",
        "so",

        "-v",
        "zos",

        "-v",
        "mlotst",

        # ----------------------------------------------------
        # SPATIAL
        # ----------------------------------------------------

        "-x",
        str(lon_min),

        "-X",
        str(lon_max),

        "-y",
        str(lat_min),

        "-Y",
        str(lat_max),

        # ----------------------------------------------------
        # TIME
        # ----------------------------------------------------

        "-t",
        start_date,

        "-T",
        end_date,

        # ----------------------------------------------------
        # SURFACE
        # ----------------------------------------------------

        "-z",
        "0.49",

        "-Z",
        "0.50",

        "--coordinates-selection-method",
        "nearest",

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        "-o",
        str(output_file.parent),

        "-f",
        output_file.name,
    ]

    subprocess.run(
        command,
        check=True,
    )

    return output_file


# ============================================================
# EXTRACT GLORYS DATA
# ============================================================

def extract_environment(
    nc_file,
    required,
):

    ds = xr.open_dataset(
        nc_file
    )

    try:

        variables = [
            "thetao",
            "uo",
            "vo",
            "so",
            "zos",
            "mlotst",
        ]

        ds = ds[
            variables
        ]

        if "depth" in ds.dims:
            ds = ds.isel(
                depth=0
            )

        if "depth" in ds.coords:
            ds = ds.drop_vars(
                "depth"
            )

        # ----------------------------------------------------
        # Coordinates of downloaded subset.
        # ----------------------------------------------------

        dl_lat = np.asarray(
            ds["latitude"].values
        )

        dl_lon = np.asarray(
            ds["longitude"].values
        )

        dl_time = pd.to_datetime(
            ds["time"].values
        ).normalize()

        # ----------------------------------------------------
        # Required coordinates.
        # ----------------------------------------------------

        req_lat = required[
            "latitude"
        ].to_numpy()

        req_lon = required[
            "longitude"
        ].to_numpy()

        lat_idx = nearest_indices(
            req_lat,
            dl_lat,
        )

        lon_idx = nearest_indices(
            req_lon,
            dl_lon,
        )

        # ----------------------------------------------------
        # Required dates.
        # ----------------------------------------------------

        req_dates = pd.to_datetime(
            required["date"]
        ).dt.normalize()

        time_lookup = {
            timestamp: index
            for index, timestamp
            in enumerate(dl_time)
        }

        time_idx = np.array(
            [
                time_lookup.get(
                    timestamp,
                    -1,
                )
                for timestamp
                in req_dates
            ],
            dtype=np.int64,
        )

        if np.any(
            time_idx < 0
        ):

            missing = req_dates[
                time_idx < 0
            ].unique()

            raise RuntimeError(
                "GLORYS file does not contain "
                f"required dates: {missing[:10]}"
            )

        # ----------------------------------------------------
        # Extract ONE VARIABLE AT A TIME.
        #
        # This is deliberate:
        # it prevents all six variables from being kept in
        # memory simultaneously.
        # ----------------------------------------------------

        thetao = ds[
            "thetao"
        ].values[
            time_idx,
            lat_idx,
            lon_idx,
        ]

        uo = ds[
            "uo"
        ].values[
            time_idx,
            lat_idx,
            lon_idx,
        ]

        vo = ds[
            "vo"
        ].values[
            time_idx,
            lat_idx,
            lon_idx,
        ]

        so = ds[
            "so"
        ].values[
            time_idx,
            lat_idx,
            lon_idx,
        ]

        zos = ds[
            "zos"
        ].values[
            time_idx,
            lat_idx,
            lon_idx,
        ]

        mlotst = ds[
            "mlotst"
        ].values[
            time_idx,
            lat_idx,
            lon_idx,
        ]

    finally:
        ds.close()

    # --------------------------------------------------------
    # Derived current speed.
    # --------------------------------------------------------

    current_speed = np.sqrt(
        uo.astype(np.float32) ** 2
        +
        vo.astype(np.float32) ** 2
    )

    result = pd.DataFrame(
        {
            "date":
                required[
                    "date"
                ].to_numpy(),

            "latitude":
                required[
                    "latitude"
                ].to_numpy(),

            "longitude":
                required[
                    "longitude"
                ].to_numpy(),

            "thetao":
                thetao.astype(
                    np.float32
                ),

            "uo":
                uo.astype(
                    np.float32
                ),

            "vo":
                vo.astype(
                    np.float32
                ),

            # KEEP SALINITY
            "so":
                so.astype(
                    np.float32
                ),

            "zos":
                zos.astype(
                    np.float32
                ),

            "mlotst":
                mlotst.astype(
                    np.float32
                ),

            "current_speed":
                current_speed.astype(
                    np.float32
                ),
        }
    )

    return result


# ============================================================
# PROCESS ONE TILE
# ============================================================

def process_tile(
    tile_number,
    total_tiles,
    tile_key,
    tile_gfw,
    year,
    month,
    month_start,
    month_end,
    temp_dir,
):

    tile_lat, tile_lon = tile_key

    print()
    print(
        f"[Tile {tile_number}/{total_tiles}] "
        f"lat={tile_lat:.0f}.."
        f"{tile_lat + TILE_SIZE:.0f}, "
        f"lon={tile_lon:.0f}.."
        f"{tile_lon + TILE_SIZE:.0f}"
    )

    # --------------------------------------------------------
    # Only one copy of the coordinates is needed.
    # --------------------------------------------------------

    required = (
        tile_gfw[
            [
                "date",
                "latitude",
                "longitude",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    lat_values = required[
        "latitude"
    ].to_numpy()

    lon_values = required[
        "longitude"
    ].to_numpy()

    # --------------------------------------------------------
    # Tight bounding box around actual required cells.
    # --------------------------------------------------------

    lat_min = max(
        GRID_LAT_MIN,
        float(lat_values.min())
        - GRID_PADDING,
    )

    lat_max = min(
        GRID_LAT_MAX,
        float(lat_values.max())
        + GRID_PADDING,
    )

    lon_min = max(
        GRID_LON_MIN,
        float(lon_values.min())
        - GRID_PADDING,
    )

    lon_max = min(
        GRID_LON_MAX,
        float(lon_values.max())
        + GRID_PADDING,
    )

    nc_file = (
        temp_dir
        /
        (
            f"glorys_"
            f"{year}_"
            f"{month:02d}_"
            f"{tile_number:04d}.nc"
        )
    )

    try:

        print(
            f"    Request: "
            f"{lat_min:.3f}..{lat_max:.3f}, "
            f"{lon_min:.3f}..{lon_max:.3f}"
        )

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        download_glorys(
            lat_min,
            lat_max,
            lon_min,
            lon_max,
            month_start.strftime(
                "%Y-%m-%d"
            ),
            month_end.strftime(
                "%Y-%m-%d"
            ),
            nc_file,
        )

        # ----------------------------------------------------
        # EXTRACT
        # ----------------------------------------------------

        result = extract_environment(
            nc_file,
            required,
        )

        # ----------------------------------------------------
        # MERGE GFW
        # ----------------------------------------------------

        result = result.merge(
            tile_gfw[
                [
                    "date",
                    "latitude",
                    "longitude",
                    "fishing_hours",
                    "total_hours",
                    "active_fishing",
                ]
            ],
            on=[
                "date",
                "latitude",
                "longitude",
            ],
            how="left",
        )

        return result

    finally:

        if nc_file.exists():

            try:
                nc_file.unlink()
            except PermissionError:
                pass


# ============================================================
# WRITE PARQUET WITHOUT KEEPING ALL TILES IN RAM
# ============================================================

def append_parquet(
    writer,
    df,
):

    table = pa.Table.from_pandas(
        df,
        preserve_index=False,
    )

    if writer is None:

        writer = pq.ParquetWriter(
            df.attrs.get(
                "_output_file"
            ),
            table.schema,
            compression="snappy",
        )

    writer.write_table(
        table
    )

    return writer


# ============================================================
# BUILD ONE MONTH
# ============================================================

def build_month(
    gfw_file,
    glorys_lat,
    glorys_lon,
    year,
    month,
    output_dir,
    temp_dir,
):

    month_start = pd.Timestamp(
        year=year,
        month=month,
        day=1,
    )

    month_end = pd.Timestamp(
        year=year,
        month=month,
        day=calendar.monthrange(
            year,
            month,
        )[1],
    )

    # --------------------------------------------------------
    # LOAD ONLY THIS MONTH.
    # --------------------------------------------------------

    gfw = load_gfw_month(
        gfw_file,
        year,
        month,
    )

    if gfw.empty:
        return

    # --------------------------------------------------------
    # ALIGN ONLY THIS MONTH.
    # --------------------------------------------------------

    gfw = align_gfw_to_glorys(
        gfw,
        glorys_lat,
        glorys_lon,
    )

    # --------------------------------------------------------
    # Free temporary objects.
    # --------------------------------------------------------

    print(
        f"Memory-safe monthly processing: "
        f"{len(gfw):,} aligned rows"
    )

    # --------------------------------------------------------
    # Create download tiles.
    # --------------------------------------------------------

    tiled = assign_tiles(
        gfw
    )

    groups = list(
        tiled.groupby(
            [
                "tile_lat",
                "tile_lon",
            ],
            sort=True,
        )
    )

    print(
        f"GLORYS download tiles: "
        f"{len(groups):,}"
    )

    print(
        f"Parallel downloads: "
        f"{MAX_WORKERS}"
    )

    # --------------------------------------------------------
    # Output file.
    # --------------------------------------------------------

    output_file = (
        output_dir
        /
        (
            f"orca_training_"
            f"{year}_"
            f"{month:02d}.parquet"
        )
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # We process tiles sequentially with respect to RAM.
    #
    # Downloads happen in at most 2 workers, but completed
    # results are written and released immediately.
    # --------------------------------------------------------

    results = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {}

        for tile_number, (
            tile_key,
            tile_gfw,
        ) in enumerate(
            groups,
            start=1,
        ):

            future = executor.submit(
                process_tile,
                tile_number,
                len(groups),
                tile_key,
                tile_gfw[
                    [
                        "date",
                        "latitude",
                        "longitude",
                        "fishing_hours",
                        "total_hours",
                        "active_fishing",
                    ]
                ].copy(),
                year,
                month,
                month_start,
                month_end,
                temp_dir,
            )

            futures[
                future
            ] = tile_number

        for future in as_completed(
            futures
        ):

            tile_number = futures[
                future
            ]

            print(
                f"    Tile {tile_number} "
                f"finished"
            )

            result = future.result()

            results.append(
                result
            )

    # --------------------------------------------------------
    # Combine only completed tile outputs.
    #
    # At this point each tile contains ONLY required cells,
    # not the full GLORYS grid.
    # --------------------------------------------------------

    if not results:
        return

    month_result = pd.concat(
        results,
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Remove exact duplicates.
    # --------------------------------------------------------

    month_result = (
        month_result
        .drop_duplicates(
            subset=[
                "date",
                "latitude",
                "longitude",
            ]
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

    # --------------------------------------------------------
    # MODIS placeholder.
    #
    # We will replace this with actual MODIS data in the
    # next stage.
    # --------------------------------------------------------

    month_result[
        "chlorophyll"
    ] = np.nan

    month_result[
        "chlorophyll_missing"
    ] = True

    # --------------------------------------------------------
    # Final schema.
    # --------------------------------------------------------

    columns = [
        "date",
        "latitude",
        "longitude",

        # GLORYS
        "thetao",
        "uo",
        "vo",
        "so",
        "zos",
        "mlotst",
        "current_speed",

        # GFW
        "fishing_hours",
        "total_hours",
        "active_fishing",

        # MODIS
        "chlorophyll",
        "chlorophyll_missing",
    ]

    month_result = month_result[
        columns
    ]

    # --------------------------------------------------------
    # Save immediately.
    # --------------------------------------------------------

    month_result.to_parquet(
        output_file,
        index=False,
        compression="snappy",
    )

    print()
    print(
        "=" * 70
    )

    print(
        f"✓ {year}-{month:02d} COMPLETE"
    )

    print(
        f"Rows: "
        f"{len(month_result):,}"
    )

    print(
        f"Fishing hours: "
        f"{month_result['fishing_hours'].sum():,.2f}"
    )

    print(
        f"Saved: "
        f"{output_file}"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Release RAM.
    # --------------------------------------------------------

    del results
    del month_result
    del gfw
    del tiled


# ============================================================
# BUILD FULL YEAR
# ============================================================

def build_year(
    year,
    gfw_file,
    grid_file,
    output_dir,
    start_month=1
):

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_dir = (
        output_dir
        / "_tmp"
    )

    temp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        # ----------------------------------------------------
        # Load tiny canonical grid.
        # ----------------------------------------------------

        glorys_lat, glorys_lon = (
            load_glorys_grid(
                grid_file
            )
        )

        # ----------------------------------------------------
        # Process month-by-month.
        # ----------------------------------------------------

        for month in range(
            start_month,
            13,
        ):

            build_month(
                gfw_file,
                glorys_lat,
                glorys_lon,
                year,
                month,
                output_dir,
                temp_dir,
            )

    finally:

        # ----------------------------------------------------
        # Cleanup temporary NetCDF files.
        # ----------------------------------------------------

        try:
            shutil.rmtree(
                temp_dir
            )
        except (
            FileNotFoundError,
            PermissionError,
        ):
            pass


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Memory-safe ORCA 2024 "
            "GFW + GLORYS builder"
        )
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--gfw",
        required=True,
    )

    parser.add_argument(
        "--glorys-grid",
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
    )

    parser.add_argument(
        "--start-month",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    build_year(
        year=args.year,
        gfw_file=Path(
            args.gfw
        ),
        grid_file=Path(
            args.glorys_grid
        ),
        output_dir=Path(
            args.output_dir
        ),
        start_month=args.start_month,
    )