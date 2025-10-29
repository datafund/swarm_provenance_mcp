#!/usr/bin/env python3
"""
Comprehensive tool validation script for the Swarm Provenance MCP server.

This script runs all tool validation tests to ensure:
1. All tools are properly defined and registered
2. Tool implementations match their definitions
3. Gateway client methods are synchronized with tools
4. Future code changes won't break tool compatibility

Usage:
    python test_tool_validation.py [--verbose] [--coverage] [--report]
"""

import sys
import subprocess
import argparse
from pathlib import Path
import json
from typing import Dict, List, Any
import asyncio


class ToolValidationRunner:
    """Runs comprehensive tool validation tests."""

    def __init__(self, verbose: bool = False, coverage: bool = False):
        self.verbose = verbose
        self.coverage = coverage
        self.results = {}
        self.project_root = Path(__file__).parent

    def run_test_suite(self, test_file: str, description: str) -> Dict[str, Any]:
        """Run a specific test suite and return results."""
        print(f"\n{'=' * 60}")
        print(f"Running: {description}")
        print(f"File: {test_file}")
        print('=' * 60)

        cmd = ["python", "-m", "pytest", f"tests/{test_file}"]

        if self.verbose:
            cmd.append("-v")

        if self.coverage:
            cmd.extend(["--cov=swarm_provenance_mcp", "--cov-report=term-missing"])

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            success = result.returncode == 0

            if self.verbose or not success:
                print("STDOUT:", result.stdout)
                if result.stderr:
                    print("STDERR:", result.stderr)

            return {
                "success": success,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "description": description
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "Test suite timed out after 5 minutes",
                "description": description
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "description": description
            }

    def run_all_tests(self) -> bool:
        """Run all tool validation test suites."""
        test_suites = [
            ("test_tool_definitions.py", "Tool Definition Validation"),
            ("test_tool_execution.py", "Tool Execution Testing"),
            ("test_tool_sync_validation.py", "Tool Synchronization Validation"),
            ("test_gateway_client.py", "Gateway Client Testing"),
            ("test_integration.py", "Integration Testing (requires gateway)")
        ]

        all_passed = True

        for test_file, description in test_suites:
            test_path = self.project_root / "tests" / test_file

            if not test_path.exists():
                print(f"\n⚠️  Warning: Test file {test_file} not found")
                continue

            result = self.run_test_suite(test_file, description)
            self.results[test_file] = result

            if result["success"]:
                print(f"✅ {description}: PASSED")
            else:
                print(f"❌ {description}: FAILED")
                all_passed = False

        return all_passed

    def generate_report(self) -> str:
        """Generate a comprehensive validation report."""
        report = []
        report.append("# Tool Validation Report")
        report.append("=" * 50)
        report.append("")

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["success"])

        report.append(f"**Summary**: {passed_tests}/{total_tests} test suites passed")
        report.append("")

        for test_file, result in self.results.items():
            status = "✅ PASSED" if result["success"] else "❌ FAILED"
            report.append(f"## {result['description']}")
            report.append(f"**Status**: {status}")
            report.append(f"**File**: {test_file}")

            if not result["success"]:
                report.append("**Error Details**:")
                report.append("```")
                report.append(result["stderr"] or "See stdout for details")
                report.append("```")

                if result["stdout"]:
                    report.append("**Test Output**:")
                    report.append("```")
                    report.append(result["stdout"][-1000:])  # Last 1000 chars
                    report.append("```")

            report.append("")

        # Add recommendations
        report.append("## Recommendations")

        if passed_tests == total_tests:
            report.append("✅ All tool validation tests passed!")
            report.append("- Your MCP server tools are properly defined and synchronized")
            report.append("- Tool implementations match their definitions")
            report.append("- Gateway client is compatible with all tools")
        else:
            report.append("⚠️  Some validation tests failed. Please address:")

            for test_file, result in self.results.items():
                if not result["success"]:
                    report.append(f"- Fix issues in {result['description']}")

        report.append("")
        report.append("## Future Maintenance")
        report.append("- Run this validation script before any major code changes")
        report.append("- Add new tests when adding new tools or modifying existing ones")
        report.append("- Update tool schemas when modifying parameter requirements")

        return "\n".join(report)

    def check_environment(self) -> bool:
        """Check if the environment is set up correctly for testing."""
        print("Checking test environment...")

        # Check if we're in the right directory
        if not (self.project_root / "swarm_provenance_mcp").exists():
            print("❌ Error: Not in the project root directory")
            return False

        # Check if tests directory exists
        if not (self.project_root / "tests").exists():
            print("❌ Error: Tests directory not found")
            return False

        # Check if pytest is available
        try:
            subprocess.run(["python", "-m", "pytest", "--version"],
                         capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ Error: pytest not available. Install with: pip install pytest")
            return False

        # Check if the package is installed
        try:
            import swarm_provenance_mcp
        except ImportError:
            print("❌ Error: swarm_provenance_mcp not installed. Run: pip install -e .")
            return False

        print("✅ Environment check passed")
        return True


def main():
    """Main entry point for the validation script."""
    parser = argparse.ArgumentParser(
        description="Validate MCP server tool definitions and implementations"
    )
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("-c", "--coverage", action="store_true",
                       help="Enable coverage reporting")
    parser.add_argument("-r", "--report", action="store_true",
                       help="Generate detailed report")
    parser.add_argument("--report-file", default="tool_validation_report.md",
                       help="Report output file (default: tool_validation_report.md)")

    args = parser.parse_args()

    runner = ToolValidationRunner(verbose=args.verbose, coverage=args.coverage)

    # Check environment first
    if not runner.check_environment():
        sys.exit(1)

    print("\n🔍 Starting MCP Tool Validation")
    print("This will validate all tool definitions, implementations, and synchronization")

    # Run all tests
    all_passed = runner.run_all_tests()

    # Generate report
    if args.report:
        report = runner.generate_report()

        report_file = Path(args.report_file)
        with open(report_file, 'w') as f:
            f.write(report)

        print(f"\n📄 Detailed report saved to: {report_file}")

    # Print summary
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TOOL VALIDATION TESTS PASSED!")
        print("Your MCP server is properly configured and synchronized.")
    else:
        print("⚠️  SOME TESTS FAILED")
        print("Please review the test output and fix any issues.")
        if args.verbose:
            print("Re-run with --report for detailed analysis.")

    print("=" * 60)

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()