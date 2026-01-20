#!/usr/bin/env python3
"""
[Utility Script] PRISMA 2020 Compliance Validator

Validates generated reports against PRISMA 2020 checklist.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.validation.prisma_validator import main

if __name__ == "__main__":
    main()
