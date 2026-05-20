#!/usr/bin/env python3
"""AI Orchestrator main entry point for python -m ai_orchestrator."""

import os
import sys
from pathlib import Path

# Add the ai_orchestrator directory to Python path
_parent = Path(__file__).resolve().parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from orchestrator import main

if __name__ == "__main__":
    # Respect ALISA_ORCHESTRATOR_DRY_RUN environment variable
    if os.environ.get('ALISA_ORCHESTRATOR_DRY_RUN') == '1':
        sys.argv.append('--dry-run')
    
    sys.exit(main())
