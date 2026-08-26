# M11-REM-08 Production Full Benchmark Plan

1. Add a failing integration test for the full runner exposed by the production app.
2. Implement the database-backed, localhost-only full benchmark adapter.
3. Wire and recreate it in the app lifespan and restore lifecycle.
4. Run focused benchmark/API tests, then the full Python and Node regression gates.
5. Run the canonical 90-attempt benchmark against the installed local model.
6. Record hardware, Ollama/model/license, settings, quality, latency, RAM/VRAM evidence,
   failures, and recommendation in a release report.
7. Review scope and commit M11-REM-08 atomically.

Do not start worker dispatch or M11-T18.
