from pathlib import Path
import argparse
import zipfile

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


# ============================================================
# INPUT COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "date",
    "cell_ll_lat",
    "cell_ll_lon",
    "fishing_hours",
    "hours",
]


# ============================================================
# PROCESS ONE YEAR
# ============================================================

def process_year(zip_file, output_file):

    zip_file = Path(zip_file)
    output_file = Path(output_file)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 75)
    print("GFW YEAR PROCESSOR")
    print("=" * 75)

    print(f"Input : {zip_file}")
    print(f"Output: {output_file}")
    print()

    writer = None

    total_input_rows = 0
    total_output_rows = 0
    total_fishing_hours = 0.0
    total_active_cells = 0

    processed_files = 0

    try:

        # ----------------------------------------------------
        # OPEN ZIP
        # ----------------------------------------------------

        with zipfile.ZipFile(
            zip_file,
            "r",
        ) as z:

            csv_files = [
                name
                for name in z.namelist()
                if name.lower().endswith(".csv")
            ]

            csv_files.sort()

            print(
                f"CSV files found: "
                f"{len(csv_files):,}"
            )

            print()

            # ------------------------------------------------
            # PROCESS EACH DAILY CSV
            # ------------------------------------------------

            for i, csv_name in enumerate(
                csv_files,
                start=1,
            ):

                print(
                    f"[{i:,}/{len(csv_files):,}] "
                    f"{csv_name}"
                )

                # --------------------------------------------
                # Read ONLY this CSV
                # --------------------------------------------

                with z.open(
                    csv_name
                ) as f:

                    df = pd.read_csv(
                        f,
                        usecols=REQUIRED_COLUMNS,
                    )

                if df.empty:

                    print(
                        "    Empty file - skipped"
                    )

                    continue

                input_rows = len(df)

                total_input_rows += (
                    input_rows
                )

                # --------------------------------------------
                # Normalize date
                # --------------------------------------------

                df["date"] = (
                    pd.to_datetime(
                        df["date"],
                        errors="coerce",
                    )
                    .dt
                    .normalize()
                )

                df = df.dropna(
                    subset=[
                        "date",
                        "cell_ll_lat",
                        "cell_ll_lon",
                    ]
                )

                # --------------------------------------------
                # Aggregate flag × gear rows
                #
                # IMPORTANT:
                #
                # This does NOT aggregate geographic regions.
                #
                # It combines multiple GFW records referring
                # to the SAME date + SAME 0.01° GFW cell.
                # --------------------------------------------

                daily = (
                    df.groupby(
                        [
                            "date",
                            "cell_ll_lat",
                            "cell_ll_lon",
                        ],
                        as_index=False,
                        sort=False,
                    )
                    .agg(
                        fishing_hours=(
                            "fishing_hours",
                            "sum",
                        ),
                        total_hours=(
                            "hours",
                            "sum",
                        ),
                    )
                )

                # --------------------------------------------
                # Active fishing
                # --------------------------------------------

                daily["active_fishing"] = (
                    daily["fishing_hours"] > 0
                ).astype("int8")

                # --------------------------------------------
                # Rename coordinates
                # --------------------------------------------

                daily = daily.rename(
                    columns={
                        "cell_ll_lat":
                            "latitude",

                        "cell_ll_lon":
                            "longitude",
                    }
                )

                # --------------------------------------------
                # Reduce numeric memory footprint
                # --------------------------------------------

                daily["latitude"] = (
                    daily["latitude"]
                    .astype("float32")
                )

                daily["longitude"] = (
                    daily["longitude"]
                    .astype("float32")
                )

                daily["fishing_hours"] = (
                    daily["fishing_hours"]
                    .astype("float32")
                )

                daily["total_hours"] = (
                    daily["total_hours"]
                    .astype("float32")
                )

                # --------------------------------------------
                # Final column order
                # --------------------------------------------

                daily = daily[
                    [
                        "date",
                        "latitude",
                        "longitude",
                        "fishing_hours",
                        "total_hours",
                        "active_fishing",
                    ]
                ]

                output_rows = len(daily)

                total_output_rows += (
                    output_rows
                )

                total_fishing_hours += (
                    float(
                        daily[
                            "fishing_hours"
                        ].sum()
                    )
                )

                total_active_cells += (
                    int(
                        daily[
                            "active_fishing"
                        ].sum()
                    )
                )

                # --------------------------------------------
                # WRITE DIRECTLY TO PARQUET
                #
                # CRITICAL:
                #
                # We do NOT append to a Python list.
                # We do NOT pd.concat().
                #
                # Each daily DataFrame is written and then
                # released from memory.
                # --------------------------------------------

                table = pa.Table.from_pandas(
                    daily,
                    preserve_index=False,
                )

                if writer is None:

                    writer = pq.ParquetWriter(
                        output_file,
                        table.schema,
                        compression="snappy",
                    )

                writer.write_table(
                    table
                )

                processed_files += 1

                print(
                    f"    Raw rows     : "
                    f"{input_rows:,}"
                )

                print(
                    f"    GFW cells    : "
                    f"{output_rows:,}"
                )

                print(
                    f"    Fishing hrs  : "
                    f"{daily['fishing_hours'].sum():,.2f}"
                )

                print()

                # --------------------------------------------
                # Explicitly release memory
                # --------------------------------------------

                del table
                del daily
                del df

    finally:

        if writer is not None:
            writer.close()

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    print("=" * 75)
    print("GFW PROCESSING COMPLETE")
    print("=" * 75)

    print(
        f"Files processed       : "
        f"{processed_files:,}"
    )

    print(
        f"Raw input rows        : "
        f"{total_input_rows:,}"
    )

    print(
        f"Processed GFW rows    : "
        f"{total_output_rows:,}"
    )

    print(
        f"Total fishing hours   : "
        f"{total_fishing_hours:,.2f}"
    )

    print(
        f"Active GFW cells      : "
        f"{total_active_cells:,}"
    )

    print(
        f"Output                : "
        f"{output_file}"
    )

    print("=" * 75)


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Memory-efficient processor for "
            "Global Fishing Watch v3 daily fleet data"
        )
    )

    parser.add_argument(
        "--zip",
        required=True,
        help="Path to GFW yearly ZIP",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where processed Parquet will be saved",
    )

    args = parser.parse_args()

    zip_file = Path(
        args.zip
    )

    output_dir = Path(
        args.output_dir
    )

    # Extract year from filename
    # Example:
    # fleet-daily-csvs-100-v3-2024.zip
    year = zip_file.stem.split("-")[-1]

    output_file = (
        output_dir
        /
        f"gfw_fishing_effort_{year}.parquet"
    )

    process_year(
        zip_file,
        output_file,
    )


if __name__ == "__main__":
    main()