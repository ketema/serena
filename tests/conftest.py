"""
Pytest configuration for Serena tests.

Adds project root to Python path to enable importing from 'contracts' package.
"""
import sys
from pathlib import Path

# Add project root to path so contracts module can be imported
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
