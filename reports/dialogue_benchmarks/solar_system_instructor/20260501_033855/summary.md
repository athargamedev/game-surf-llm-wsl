# Dialogue Benchmark: solar_system_instructor

- Run ID: `20260501_033855`
- Benchmark: `benchmarks/npc_dialogue/solar_system_instructor.json`
- Passed: 2/5

## Cases
- inner_planets_rocky: check (required_terms:2/3)
- astronomical_unit_scale: pass (none)
- small_bodies_formation: pass (none)
- off_topic_redirect: check (required_terms:0/1, forbidden_terms:database index)
- cross_session_jupiter_memory: check (too_short:48<100)
