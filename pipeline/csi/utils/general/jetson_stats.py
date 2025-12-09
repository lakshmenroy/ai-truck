import sys
import pandas as pd
from jtop import jtop
from pathlib import Path
from datetime import datetime

FILE = Path(__file__).resolve()
ROOT = FILE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def main() -> None:
    """
    This function is used to monitor and save Jetson 
    performance data as a CSV file.

    :return: None.
    """
    data = []

    print(f"\nStarting measuring Tegra stats until CTRL+C\n")

    try:
        with jtop() as jetson:
            # jetson.ok() will provide the proper update frequency
            while jetson.ok():
                try:
                    # Read tegra stats
                    data.append(jetson.stats)
                except KeyboardInterrupt:
                    break
    finally:
        now = datetime.now()
        timestamp = now.strftime(format="%Y-%m-%d-%H-%M-%S")
        path = ROOT / f"tegra_stats_{timestamp}.csv"
        print(f"\nSaving Tegra stats to:\n{path}\n")
        
        df = pd.DataFrame(data=data)
        df.to_csv(path_or_buf=path, index=False)
        

if __name__ == "__main__":
    main()