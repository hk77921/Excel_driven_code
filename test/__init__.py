"""
Test Package for Excel-Driven Trading Bot
========================================

This package contains all test files and example scripts.

Test files can be run individually or through the main entry point:
    python main.py --mode test

Available test modules:
- test_production_ready: Comprehensive production readiness tests
- test_paper_trading: Paper trading functionality tests  
- test_integration: Integration tests
- test_simple_paper: Simple paper trading tests
- test_standalone_paper: Standalone paper trading tests
"""

import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)