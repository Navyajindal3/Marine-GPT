from pathlib import Path
import argparse
import subprocess


DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"


def run_subset(
    variables,
    lon_min,
    lon_max,
    lat_min,
    lat_max,
    start_date,
    end_date,
    depth_min=None,
    depth_max=None,
    output_dir=None,
    filename=None,
):
    command = [
        "copernicusmarine",
        "subset",
        "-i", DATASET_ID,
    ]

    for variable in variables:
        command.extend(["-v", variable])

    command.extend([
        "-x", str(lon_min),
        "-X", str(lon_max),
        "-y", str(lat_min),
        "-Y", str(lat_max),
        "-t", start_date,
        "-T", end_date,
        "--coordinates-selection-method", "nearest",
        "-o", str(output_dir),
        "-f", filename,
    ])

    if depth_min is not None:
        command.extend(["-z", str(depth_min)])
        command.extend(["-Z", str(depth_max)])

    print("\nRunning:")
    print(" ".join(command))
    print()

    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Extract a small GLORYS spatial-temporal dataset"
    )

    parser.add_argument("--lon-min", type=float, required=True)
    parser.add_argument("--lon-max", type=float, required=True)
    parser.add_argument("--lat-min", type=float, required=True)
    parser.add_argument("--lat-max", type=float, required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Surface variables
    run_subset(
        variables=["zos", "mlotst"],
        lon_min=args.lon_min,
        lon_max=args.lon_max,
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=output_dir,
        filename="glorys_surface.nc",
    )

    # Near-surface 3-D variables
    run_subset(
        variables=["thetao", "uo", "vo", "so"],
        lon_min=args.lon_min,
        lon_max=args.lon_max,
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        start_date=args.start_date,
        end_date=args.end_date,
        depth_min=0.49,
        depth_max=0.50,
        output_dir=output_dir,
        filename="glorys_3d.nc",
    )

    print("\nExtraction complete.")
    print(f"Files saved to: {output_dir}")


if __name__ == "__main__":
    main()