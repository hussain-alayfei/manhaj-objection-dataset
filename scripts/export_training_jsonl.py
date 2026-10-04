from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cli import main
sys.argv = [sys.argv[0], 'export', *sys.argv[1:], *[]]
if __name__ == '__main__': main()
