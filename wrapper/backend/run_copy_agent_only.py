#!/usr/bin/env python3
"""
Run ONLY the copy agent (Step 10) on an existing enriched CSV or DataFrame.

Usage:
    python run_copy_agent_only.py --csv /path/to/enriched_leads.csv --output-dir /path/to/output

    OR:
    python run_copy_agent_only.py --csv /path/to/leads.csv --product Empuls --vertical Healthcare

    OR (programmatically):
    from run_copy_agent_only import run_copy_agent_on_csv
    result = run_copy_agent_on_csv("leads.csv", output_dir="output", product_hint="Empuls")
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.pipeline import copy_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_copy_agent_on_csv(
    csv_path: str,
    output_dir: str = "./output",
    campaign_title: str = None,
    product_hint: str = None,
    vertical_hint: str = None,
) -> dict:
    """
    Run copy agent on an existing enriched CSV.

    Args:
        csv_path: Path to CSV with enriched leads (must have 'email' column)
        output_dir: Where to write output files (10_copy_agent.json + 10_COPY_AGENT.md)
        campaign_title: Optional campaign name (for output markdown header)
        product_hint: Override product detection (Empuls, Plum, Compass, Loyalife)
        vertical_hint: Override vertical detection (Healthcare, Finance, Tech, Retail)

    Returns:
        dict with status, lead_count, persona_detected, and copy
    """

    # Validate input
    csv_path = Path(csv_path)
    if not csv_path.exists():
        logger.error(f"CSV not found: {csv_path}")
        return {"status": "error", "message": f"CSV not found: {csv_path}"}

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not campaign_title:
        campaign_title = csv_path.stem

    # Load CSV
    logger.info(f"Loading CSV: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return {"status": "error", "message": f"Failed to read CSV: {e}"}

    logger.info(f"Loaded {len(df)} rows from {csv_path}")

    # Validate required columns
    if "email" not in df.columns:
        logger.error("CSV must have 'email' column")
        return {"status": "error", "message": "CSV must have 'email' column"}

    # Run copy agent
    logger.info("Running copy agent...")
    persona_hints = {}
    if product_hint:
        persona_hints["primary_product"] = product_hint
    if vertical_hint:
        persona_hints["vertical"] = vertical_hint

    result = copy_agent.run(df, persona_hints=persona_hints if persona_hints else None)

    # Write outputs
    if result["status"] == "done":
        logger.info(f"✅ Copy agent succeeded. Detected: {result['persona_detected']['persona_type']} | {result['persona_detected']['primary_product']}")

        # Write JSON
        json_path = output_dir / "10_copy_agent.json"
        with open(json_path, "w") as f:
            json.dump(result["copy"], f, indent=2)
        logger.info(f"✅ Wrote JSON: {json_path}")

        # Write Markdown
        md_path = output_dir / "10_COPY_AGENT.md"
        markdown = copy_agent.build_markdown(campaign_title, result)
        with open(md_path, "w") as f:
            f.write(markdown)
        logger.info(f"✅ Wrote Markdown: {md_path}")

        # Write persona summary
        persona_path = output_dir / "persona_detected.json"
        with open(persona_path, "w") as f:
            json.dump(result["persona_detected"], f, indent=2)
        logger.info(f"✅ Wrote persona: {persona_path}")
    else:
        logger.warning(f"⚠️  Copy agent status: {result['status']}")
        logger.warning(f"   Message: {result.get('message', 'No message')}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run copy agent (Step 10) on enriched leads CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic: run on enriched CSV
  python run_copy_agent_only.py --csv leads.csv

  # With output directory
  python run_copy_agent_only.py --csv leads.csv --output-dir ./output

  # With persona hints (override auto-detection)
  python run_copy_agent_only.py --csv leads.csv --product Empuls --vertical Healthcare

  # Custom campaign title
  python run_copy_agent_only.py --csv leads.csv --title "Q2-2026 Empuls Healthcare"
        """
    )

    parser.add_argument("--csv", required=True, help="Path to enriched leads CSV")
    parser.add_argument("--output-dir", default="./output", help="Output directory (default: ./output)")
    parser.add_argument("--title", help="Campaign title (default: CSV filename)")
    parser.add_argument("--product", choices=["Empuls", "Plum", "Compass", "Loyalife"],
                       help="Override product detection")
    parser.add_argument("--vertical", choices=["Healthcare", "Finance", "Tech", "Retail"],
                       help="Override vertical detection")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("COPY AGENT (STEP 10 ONLY)")
    logger.info("=" * 80)
    logger.info(f"CSV: {args.csv}")
    logger.info(f"Output: {args.output_dir}")
    if args.title:
        logger.info(f"Title: {args.title}")
    if args.product:
        logger.info(f"Product hint: {args.product}")
    if args.vertical:
        logger.info(f"Vertical hint: {args.vertical}")
    logger.info("=" * 80)

    result = run_copy_agent_on_csv(
        csv_path=args.csv,
        output_dir=args.output_dir,
        campaign_title=args.title,
        product_hint=args.product,
        vertical_hint=args.vertical,
    )

    logger.info("=" * 80)
    logger.info(f"Status: {result['status']}")
    if result["status"] == "done":
        logger.info(f"Lead count: {result['lead_count']}")
        logger.info(f"Persona: {result['persona_detected']['persona_type']}")
        logger.info(f"Product: {result['persona_detected']['primary_product']}")
        logger.info(f"Use case: {result['persona_detected']['use_case']}")
    else:
        logger.error(f"Error: {result.get('message', result['status'])}")
        sys.exit(1)
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
