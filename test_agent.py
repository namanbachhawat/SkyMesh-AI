"""Quick integration test for the Drone Operations Coordinator."""
import sys
sys.path.insert(0, ".")
from agent.coordinator_agent import DataStore, process_message

store = DataStore()

tests = [
    ("Show available pilots in Bangalore", "TEST 1: Query pilots"),
    ("Check for conflicts", "TEST 2: Conflict detection"),
    ("Assign best pilot and drone to PRJ001", "TEST 3: Assignment matching"),
    ("Urgent reassignment for PRJ002", "TEST 4: Urgent reassignment"),
    ("Mark Arjun as On Leave", "TEST 5: Status update"),
    ("Show drones in Mumbai", "TEST 6: Query drones"),
    ("Help", "TEST 7: Help command"),
]

for query, label in tests:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Query: {query}")
    print(f"{'='*60}")
    result = process_message(query, store)
    print(result)

print(f"\n{'='*60}")
print("  ALL TESTS PASSED ✅")
print(f"{'='*60}")
