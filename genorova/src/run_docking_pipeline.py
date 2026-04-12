#!/usr/bin/env python3
"""
Genorova AI — Run Docking Pipeline (CLI)
========================================

ENTRY POINT: execute complete molecular docking pipeline

USAGE:
    python run_docking_pipeline.py [OPTIONS]

OPTIONS:
    --target {diabetes|infection|all}  Run docking for specific target
    --max-molecules N                  Limit to first N candidates (for testing)
    --no-visualization                 Skip visualization generation
    --help                             Show this help message

EXAMPLES:
    # Run complete pipeline for all targets
    python run_docking_pipeline.py

    # Test with diabetes target, limit to 10 molecules
    python run_docking_pipeline.py --target diabetes --max-molecules 10

    # Run infection docking without visualizations
    python run_docking_pipeline.py --target infection --no-visualization

OUTPUT RESULTS:
    outputs/docking/diabetes_docking_results.csv
    outputs/docking/infection_docking_results.csv
    outputs/docking/results/diabetes_final_ranked_candidates.csv
    outputs/docking/results/infection_final_ranked_candidates.csv
    outputs/docking/visualizations/

AUTHOR: Claude Code (Pushp Dwivedi)
DATE: April 2026
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
SRC_PATH = Path(__file__).parent
sys.path.insert(0, str(SRC_PATH))

print("[CLI] Genorova AI v1.0 — Molecular Docking Pipeline")
print("[CLI] Loading modules...\n")

try:
    from docking.batch_processor import run_complete_docking_pipeline
    print("[CLI] ✓ All modules loaded successfully\n")
except ImportError as e:
    print(f"[ERROR] Failed to load docking modules: {str(e)}")
    print("\n[HELP] Make sure you're in the genorova/src directory:")
    print("  cd genorova/src")
    print("  python run_docking_pipeline.py")
    sys.exit(1)


# ============================================================================
# CLI ARGUMENT PARSING
# ============================================================================

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Genorova AI — Molecular Docking Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Complete pipeline
  python run_docking_pipeline.py

  # Test mode (10 molecules)
  python run_docking_pipeline.py --max-molecules 10

  # Diabetes only
  python run_docking_pipeline.py --target diabetes

  # Infection only, no visualizations
  python run_docking_pipeline.py --target infection --no-visualization
        """
    )
    
    parser.add_argument(
        '--target',
        choices=['diabetes', 'infection', 'all'],
        default='all',
        help='Target disease (default: all)'
    )
    
    parser.add_argument(
        '--max-molecules', '-m',
        type=int,
        default=None,
        help='Limit to N molecules (for testing)'
    )
    
    parser.add_argument(
        '--no-visualization',
        action='store_true',
        help='Skip visualization generation'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Genorova AI v1.0 (April 2026)'
    )
    
    return parser.parse_args()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main CLI entry point."""
    
    print("="*70)
    print("GENOROVA AI — MOLECULAR DOCKING PIPELINE (CLI)")
    print("="*70)
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Parse arguments
    args = parse_arguments()
    
    # Display configuration
    print("[CONFIG] Pipeline Configuration:")
    print(f"  Target:        {args.target}")
    print(f"  Max molecules: {args.max_molecules or 'No limit'}")
    print(f"  Visualization: {'Enabled' if not args.no_visualization else 'Disabled'}")
    print()
    
    # Run pipeline
    try:
        print("[START] Running docking pipeline...\n")
        
        result = run_complete_docking_pipeline(max_mols=args.max_molecules)
        
        # Print results summary
        print("\n" + "="*70)
        print("PIPELINE SUMMARY")
        print("="*70)
        
        if result['success']:
            for target in ['diabetes', 'infection']:
                if target in result['targets']:
                    target_result = result['targets'][target]
                    print(f"\n{target.upper()}:")
                    print(f"  ✓ Candidates processed:     {target_result['total_candidates']}")
                    print(f"  ✓ With docking data:        {target_result['with_docking_data']}")
                    if target_result['mean_affinity'] is not None:
                        print(f"  ✓ Mean binding affinity:    {target_result['mean_affinity']:>8.2f} kcal/mol")
                    if target_result['mean_combined_score'] is not None:
                        print(f"  ✓ Mean combined score:      {target_result['mean_combined_score']:>8.4f}")
                    print(f"  ✓ Results file:             {Path(target_result['results_file']).name}")
            
            print("\n" + "="*70)
            print("✓ PIPELINE COMPLETED SUCCESSFULLY")
            print("="*70)
            print("\nOUTPUT FILES:")
            print("  • outputs/docking/diabetes_docking_results.csv")
            print("  • outputs/docking/infection_docking_results.csv")
            print("  • outputs/docking/results/")
            print("  • outputs/docking/visualizations/")
            print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            return 0
        else:
            print(f"\n✗ PIPELINE FAILED")
            print(f"Error: {result.get('error', 'Unknown error')}")
            return 1
    
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Pipeline stopped by user")
        return 130
    
    except Exception as e:
        print(f"\n[FATAL ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
