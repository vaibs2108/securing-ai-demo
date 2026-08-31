import sys
import os

print("Starting import verification check...")

modules_to_test = [
    "app.data.generator",
    "app.kpi.engine",
    "app.llm.router",
    "app.ui.components.lifecycle_stage",
    "app.runtime.agent_manager",
    "app.mcp.registry",
    "app.mcp.client",
    "app.guardrails.validator",
    "app.observability.hallucination",
    "app.observability.score_history",
    "backend.main",
]

failures = 0
for mod in modules_to_test:
    try:
        print(f"Testing {mod}...", end=" ")
        __import__(mod)
        print("SUCCESS")
    except Exception as e:
        print("FAILED")
        import traceback
        traceback.print_exc()
        failures += 1

if failures > 0:
    print(f"\nVerification finished with {failures} failures.")
    sys.exit(1)
else:
    print("\nAll core modules imported successfully! Codebase structural integrity verified.")
    sys.exit(0)
