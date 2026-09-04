"""
Standalone CLI demo for the Hardware Profiling Module.

Run this to see HP-1 to HP-5 working with zero dependency on the network,
Docker, or WebTorrent modules — matches MVP Build Order step 1
("standalone, testable without network").

    python demo.py
"""

import json

from profiler import HardwareProfiler


def main():
    print("=== ComputeTorrent Seeder — Hardware Profiling Demo ===\n")

    profiler = HardwareProfiler()  # HP-1: profiles on launch

    print("Node Profile (HP-2):")
    print(json.dumps(profiler.profile.to_json(), indent=2))

    print(f"\nAssigned Tier (HP-3): Tier-{profiler.tier}")

    print("\nUI-facing summary (HP-5):")
    print(f"  {profiler.summary()}")

    print("\nPayload the Networking Client would send in `register` (section 7):")
    print(json.dumps(profiler.registration_payload(), indent=2))

    print("\n--- Simulating manual 'Refresh' action (HP-4) ---")
    profiler.refresh()
    print(f"  {profiler.summary()}")


if __name__ == "__main__":
    main()
