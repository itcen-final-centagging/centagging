"""`python -m crawl` 실행을 지원합니다. / Supports `python -m crawl`."""

import sys

from crawl import main

if __name__ == "__main__":
    sys.exit(main.main(sys.argv[1:]))
