from pathlib import Path
import calendar
import re

import earthaccess
import numpy as np
import pandas as pd
import xarray as xr


# ============================================================
# CONFIG
# ============================================================

YEAR = 2024

TRAINING_DIR = Path("data/training/2024")
MODIS_DIR = Path("data/modis/2024")

MODIS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CONCEPT_ID = "C3380709133-OB_CLOUD"

SHORT_NAME = "MODISA_L3m_CHL"

FILENAME_PATTERN = re.compile(
    r"AQUA_MODIS\.(\d{8})\.L3m\.DAY\.CHL\.chlor_a\.9km\.nc$"
)


# ============================================================
# EARTHDATA LOGIN
# ============================================================

def login():

    print()
    print("=" * 70)
    print("NASA EARTHDATA LOGIN")
    print("=" * 70)

    auth = earthaccess.login(
        strategy="interactive",
    )

    if not auth.authenticated:
        raise RuntimeError(
            "NASA Earthdata authentication failed."
        )

    print("✓ Earthdata authentication successful")


# ============================================================
# FIND EXACT MODIS GRANULE
# ============================================================

def find_modis_granule(date):

    date_string = date.strftime("%Y%m%d")

    filename = (
        f"AQUA_MODIS."
        f"{date_string}."
        f"L3m.DAY.CHL.chlor_a.9km.nc"
    )

    print(
        f"Using exact MODIS file: {filename}"
    )

    # --------------------------------------------------------
    # Earthdata OB.CLOUD public object.
    # This is the exact archive location for the MODIS
    # Level-3 mapped 9-km chlorophyll product.
    # --------------------------------------------------------

    url = (
        "https://obdaac-tea.earthdatacloud.nasa.gov/"
        "ob-cumulus-prod-public/"
        + filename
    )

    print(
        f"URL: {url}"
    )

    return url


# ============================================================
# DOWNLOAD ONE DAY
# ============================================================

def download_day(date):
    date_string = date.strftime("%Y%m%d")
    filename = f"AQUA_MODIS.{date_string}.L3m.DAY.CHL.chlor_a.9km.nc"

    output_path = MODIS_DIR / filename

    if output_path.exists():
        print(f"Already downloaded: {filename}")
        return output_path

    print(f"Searching MODIS granule: {date_string}")

    results = earthaccess.search_data(
        concept_id="C3380709133-OB_CLOUD",
        temporal=(date_string, date_string),
    )

    # Find the exact 9 km daily chlorophyll product
    matches = []

    for result in results:
        for link in result.data_links():
            if link.endswith(filename):
                matches.append(link)

    # Remove duplicate URLs
    matches = list(dict.fromkeys(matches))

    if not matches:
        raise RuntimeError(
            f"Could not find exact MODIS file for {date_string}\n"
            f"Expected: {filename}\n"
            f"Earthdata returned {len(results)} granules."
        )

    print(f"Found: {matches[0]}")

    # earthaccess handles authentication
    downloaded = earthaccess.download(
        [matches[0]],
        local_path=str(MODIS_DIR)
    )

    if not downloaded:
        raise RuntimeError(f"Earthaccess failed to download {filename}")

    # earthaccess may return the actual downloaded path
    downloaded_path = Path(downloaded[0])

    if downloaded_path != output_path and downloaded_path.exists():
        downloaded_path.replace(output_path)

    print(f"Downloaded: {output_path}")

    return output_path


# ============================================================
# EXTRACT MODIS VALUES
# ============================================================

def extract_modis_values(
    nc_file,
    required,
):

    ds = xr.open_dataset(
        nc_file
    )

    try:

        # ----------------------------------------------------
        # MODIS coordinates
        # ----------------------------------------------------

        lat = np.asarray(
            ds["lat"].values,
            dtype=np.float64,
        )

        lon = np.asarray(
            ds["lon"].values,
            dtype=np.float64,
        )

        chlor = ds[
            "chlor_a"
        ].values

        # ----------------------------------------------------
        # MODIS latitude is descending.
        #
        # nearest_indices below expects sorted ascending
        # coordinates, so reverse latitude if necessary.
        # ----------------------------------------------------

        if lat[0] > lat[-1]:

            lat = lat[::-1]
            chlor = chlor[::-1, :]

        # ----------------------------------------------------
        # MODIS longitude should be ascending.
        # ----------------------------------------------------

        if lon[0] > lon[-1]:

            lon = lon[::-1]
            chlor = chlor[:, ::-1]

        # ----------------------------------------------------
        # Required GLORYS coordinates.
        # ----------------------------------------------------

        req_lat = (
            required["latitude"]
            .to_numpy(
                dtype=np.float64
            )
        )

        req_lon = (
            required["longitude"]
            .to_numpy(
                dtype=np.float64
            )
        )

        # ----------------------------------------------------
        # Nearest MODIS pixel.
        # ----------------------------------------------------

        lat_idx = nearest_indices(
            req_lat,
            lat,
        )

        lon_idx = nearest_indices(
            req_lon,
            lon,
        )

        values = chlor[
            lat_idx,
            lon_idx,
        ]

        return values.astype(
            np.float32
        )

    finally:

        ds.close()


# ============================================================
# NEAREST INDEX
# ============================================================

def nearest_indices(
    values,
    grid,
):

    values = np.asarray(
        values,
        dtype=np.float64,
    )

    grid = np.asarray(
        grid,
        dtype=np.float64,
    )

    idx = np.searchsorted(
        grid,
        values,
    )

    idx = np.clip(
        idx,
        1,
        len(grid) - 1,
    )

    left = grid[
        idx - 1
    ]

    right = grid[
        idx
    ]

    choose_right = (
        np.abs(
            values - right
        )
        <
        np.abs(
            values - left
        )
    )

    idx = (
        idx
        -
        (~choose_right)
    )

    return idx.astype(
        np.int64
    )


# ============================================================
# PROCESS ONE MONTH
# ============================================================

def process_month(
    month,
):

    training_file = (
        TRAINING_DIR
        /
        (
            f"orca_training_"
            f"{YEAR}_"
            f"{month:02d}.parquet"
        )
    )

    if not training_file.exists():

        raise FileNotFoundError(
            f"Training file missing: "
            f"{training_file}"
        )

    print()
    print("=" * 70)
    print(
        f"PROCESSING {YEAR}-{month:02d}"
    )
    print("=" * 70)

    df = pd.read_parquet(
        training_file
    )

    df["date"] = pd.to_datetime(
        df["date"]
    ).dt.normalize()

    print(
        f"Training rows: {len(df):,}"
    )

    # --------------------------------------------------------
    # Only unique date + location combinations need extraction.
    # --------------------------------------------------------

    required = (
        df[
            [
                "date",
                "latitude",
                "longitude",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    print(
        f"Unique date/location combinations: "
        f"{len(required):,}"
    )

    required["chlorophyll"] = np.nan

    # --------------------------------------------------------
    # Process each day separately.
    # --------------------------------------------------------

    dates = (
        required["date"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    for day_number, date in enumerate(
        dates,
        start=1,
    ):

        date = pd.Timestamp(
            date
        )

        print(
            f"\n[{day_number}/{len(dates)}] "
            f"{date.date()}"
        )

        day_mask = (
            required["date"]
            == date
        )

        day_required = (
            required.loc[
                day_mask,
                [
                    "date",
                    "latitude",
                    "longitude",
                ],
            ]
            .reset_index()
        )

        nc_file = download_day(
            date
        )

        values = extract_modis_values(
            nc_file,
            day_required,
        )

        required.loc[
            day_required["index"],
            "chlorophyll",
        ] = values

        valid = np.isfinite(
            values
        ).sum()

        print(
            f"Valid chlorophyll: "
            f"{valid:,} / {len(values):,}"
        )

    # --------------------------------------------------------
    # Merge chlorophyll into the full training dataframe.
    # --------------------------------------------------------

    df = df.drop(
        columns=[
            "chlorophyll",
            "chlorophyll_missing",
        ],
        errors="ignore",
    )

    df = df.merge(
        required[
            [
                "date",
                "latitude",
                "longitude",
                "chlorophyll",
            ]
        ],
        on=[
            "date",
            "latitude",
            "longitude",
        ],
        how="left",
    )

    # --------------------------------------------------------
    # Missingness flag.
    # --------------------------------------------------------

    df[
        "chlorophyll_missing"
    ] = (
        ~np.isfinite(
            df["chlorophyll"]
            .to_numpy()
        )
    )

    # --------------------------------------------------------
    # Restore final column order.
    # --------------------------------------------------------

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

        "fishing_hours",
        "total_hours",
        "active_fishing",

        "chlorophyll",
        "chlorophyll_missing",
    ]

    df = df[
        columns
    ]

    # --------------------------------------------------------
    # Write through temporary file.
    # This protects the existing monthly file if anything
    # fails during processing.
    # --------------------------------------------------------

    temp_file = (
        training_file
        .with_suffix(
            ".modis_tmp.parquet"
        )
    )

    df.to_parquet(
        temp_file,
        index=False,
        compression="snappy",
    )

    # Replace original only after successful write.
    temp_file.replace(
        training_file
    )

    print()
    print(
        f"✓ {YEAR}-{month:02d} MODIS COMPLETE"
    )

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"Valid chlorophyll: "
        f"{df['chlorophyll'].notna().sum():,}"
    )

    print(
        f"Missing chlorophyll: "
        f"{df['chlorophyll_missing'].sum():,}"
    )

    print(
        f"Updated: {training_file}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    login()

    for month in range(
        1,
        13,
    ):

        process_month(
            month
        )

    print()
    print("=" * 70)
    print("✓ ALL 2024 MODIS PROCESSING COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()