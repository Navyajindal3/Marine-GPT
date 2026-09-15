from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

GFW_FILE = Path("data/gfw_processed/gfw_fishing_effort_2012.parquet")
GLORYS_FILE = Path("data/alignment_test/glorys_cluster.parquet")
MODIS_FILE = Path(
    "data/alignment_test/modis/"
    "AQUA_MODIS.20120327.L3m.DAY.CHL.chlor_a.9km.nc"
)

OUTPUT_FILE = Path(
    "data/alignment_test/"
    "orca_training_alignment_test.parquet"
)


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Calculate great-circle distance between two coordinates.
    """
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def main():

    print("Loading GFW...")
    gfw = pd.read_parquet(GFW_FILE)

    # Only the date we are validating
    gfw = gfw[
        (gfw["date"] == "2012-03-27")
        & (gfw["latitude"].between(1.8, 2.2))
        & (gfw["longitude"].between(55.8, 56.3))
    ].copy()

    print(f"GFW rows: {len(gfw)}")

    print("\nLoading GLORYS...")
    glorys = pd.read_parquet(GLORYS_FILE)

    print(f"GLORYS rows: {len(glorys)}")

    # ---------------------------------------------------------
    # Match every GFW observation to nearest GLORYS grid point
    # ---------------------------------------------------------

    glorys_coords = glorys[
        ["latitude", "longitude"]
    ].drop_duplicates().reset_index(drop=True)

    matched_rows = []

    for _, row in gfw.iterrows():

        distances = haversine_km(
            row["latitude"],
            row["longitude"],
            glorys_coords["latitude"].values,
            glorys_coords["longitude"].values,
        )

        idx = np.argmin(distances)

        matched_rows.append(
            {
                "glorys_latitude": glorys_coords.iloc[idx]["latitude"],
                "glorys_longitude": glorys_coords.iloc[idx]["longitude"],
                "glorys_distance_km": distances[idx],
            }
        )

    glorys_match = pd.DataFrame(matched_rows)

    aligned = pd.concat(
        [
            gfw.reset_index(drop=True),
            glorys_match,
        ],
        axis=1,
    )

    # Join the actual GLORYS variables
    aligned = aligned.merge(
        glorys,
        left_on=[
            "date",
            "glorys_latitude",
            "glorys_longitude",
        ],
        right_on=[
            "date",
            "latitude",
            "longitude",
        ],
        how="left",
        suffixes=("", "_glorys"),
    )

    # Remove duplicate environmental coordinate columns
    aligned = aligned.drop(
        columns=["latitude_glorys", "longitude_glorys"],
        errors="ignore",
    )

    # ---------------------------------------------------------
    # MODIS chlorophyll
    # ---------------------------------------------------------

    print("\nLoading MODIS...")
    ds = xr.open_dataset(MODIS_FILE)

    chlorophyll = ds["chlor_a"]

    modis_values = []
    modis_lats = []
    modis_lons = []
    modis_distances = []

    for _, row in aligned.iterrows():

        # Find nearest MODIS pixel
        value = chlorophyll.sel(
            lat=row["latitude"],
            lon=row["longitude"],
            method="nearest",
        )

        modis_lat = float(value["lat"].values)
        modis_lon = float(value["lon"].values)
        modis_value = float(value.values)

        distance = haversine_km(
            row["latitude"],
            row["longitude"],
            modis_lat,
            modis_lon,
        )

        modis_values.append(modis_value)
        modis_lats.append(modis_lat)
        modis_lons.append(modis_lon)
        modis_distances.append(distance)

    aligned["chlorophyll"] = modis_values
    aligned["modis_latitude"] = modis_lats
    aligned["modis_longitude"] = modis_lons
    aligned["modis_distance_km"] = modis_distances

    # ---------------------------------------------------------
    # Final column order
    # ---------------------------------------------------------

    columns = [
        "date",
        "latitude",
        "longitude",

        "fishing_hours",
        "total_hours",
        "active_fishing",

        "thetao",
        "uo",
        "vo",
        "so",
        "zos",
        "mlotst",
        "current_speed",

        "chlorophyll",

        "glorys_latitude",
        "glorys_longitude",
        "glorys_distance_km",

        "modis_latitude",
        "modis_longitude",
        "modis_distance_km",
    ]

    aligned = aligned[columns]

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    aligned.to_parquet(
        OUTPUT_FILE,
        index=False,
    )

    print("\nAligned dataset:")
    print(aligned.to_string(index=False))

    print("\nShape:")
    print(aligned.shape)

    print("\nMissing values:")
    print(aligned.isna().sum())

    print("\nMatching distances:")
    print(
        aligned[
            [
                "glorys_distance_km",
                "modis_distance_km",
            ]
        ].describe()
    )

    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()