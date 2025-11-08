import sys
from . import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted by user.\n")
        sys.exit(130)

