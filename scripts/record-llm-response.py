#!/usr/bin/env python3
"""
Helper script to record problematic LLM responses for regression testing.

Usage:
    python scripts/record-llm-response.py "response text" "context/description"
    python scripts/record-llm-response.py --file response.txt "context"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path


def record_response(
    response_text: str,
    context: str,
    output_file: str = None,
    append: bool = True,
):
    """
    Record an LLM response to the fixtures file.
    
    Args:
        response_text: The problematic LLM response text
        context: Description of when/how this occurred
        output_file: Optional custom output file path
        append: Whether to append to existing file (default) or overwrite
    """
    # Default output location
    if output_file is None:
        project_root = Path(__file__).parent.parent
        output_file = project_root / "tests" / "fixtures" / "recorded_llm_responses.py"
    else:
        output_file = Path(output_file)
    
    # Generate variable name from context
    timestamp = datetime.now().strftime("%Y%m%d")
    var_name = context.upper().replace(" ", "_").replace("-", "_")
    var_name = "".join(c for c in var_name if c.isalnum() or c == "_")
    var_name = f"{var_name}_{timestamp}"
    
    # Format the entry
    entry = f'''
# Context: {context}
# Recorded: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
{var_name} = """{response_text}"""
'''
    
    # Write to file
    mode = "a" if append else "w"
    try:
        with open(output_file, mode) as f:
            f.write(entry)
        
        print(f"SUCCESS: Response recorded to {output_file}")
        print(f"Variable name: {var_name}")
        print("")
        print("Next steps:")
        print(f"1. Import in your test: from tests.fixtures.recorded_llm_responses import {var_name}")
        print("2. Create a regression test using this fixture")
        print("3. Verify your fix handles this response gracefully")
        return True
    except Exception as e:
        print(f"ERROR: Failed to write to {output_file}: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Record problematic LLM responses for regression testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Record from command line
  python scripts/record-llm-response.py "DECISION: include" "Paper 5 crash"
  
  # Record from file
  python scripts/record-llm-response.py --file response.txt "Malformed JSON bug"
  
  # Custom output location
  python scripts/record-llm-response.py "response" "context" --output custom.py
        """,
    )
    
    parser.add_argument(
        "response",
        nargs="?",
        help="The LLM response text to record (or use --file)",
    )
    
    parser.add_argument(
        "context",
        help="Description of the issue (e.g., 'Paper 5 crash', 'Malformed JSON')",
    )
    
    parser.add_argument(
        "--file",
        "-f",
        help="Read response from file instead of command line",
    )
    
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: tests/fixtures/recorded_llm_responses.py)",
    )
    
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output file instead of appending",
    )
    
    args = parser.parse_args()
    
    # Get response text
    if args.file:
        try:
            with open(args.file, "r") as f:
                response_text = f.read()
        except Exception as e:
            print(f"ERROR: Failed to read file {args.file}: {e}", file=sys.stderr)
            return 1
    elif args.response:
        response_text = args.response
    else:
        print("ERROR: Must provide response text or --file", file=sys.stderr)
        parser.print_help()
        return 1
    
    # Record the response
    success = record_response(
        response_text=response_text,
        context=args.context,
        output_file=args.output,
        append=not args.overwrite,
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
