from pathlib import Path
import argparse
import xarray as xr


def inspect_grid(file_path):
    print(f"Opening: {file_path}")

    ds = xr.open_dataset(file_path)

    print("\nDimensions:")
    for name, size in ds.sizes.items():
        print(f"  {name}: {size:,}")

    print("\nCoordinates:")

    for name in ["latitude", "longitude", "lat", "lon"]:
        if name in ds.coords:
            values = ds[name].values

            print(f"\n{name}:")
            print(f"  size: {len(values):,}")
            print(f"  first: {values[0]}")
            print(f"  second: {values[1]}")
            print(f"  last: {values[-1]}")

            if len(values) > 1:
                print(f"  spacing: {values[1] - values[0]}")

    ds.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--file",
        required=True
    )

    args = parser.parse_args()

    inspect_grid(Path(args.file))