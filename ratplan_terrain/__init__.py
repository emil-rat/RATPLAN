"""RATPLAN's mission-planner library.

Currently just the real-terrain plumbing (architecture.md §6's target layout, seeded early since ratmap
itself already depends on `ratplan_terrain.primitives.terrain.DtmSampler`): WGS84 geometry, DTM sampling over a
ratmap-supplied GeoTIFF, and the bridge from a sampled DTM into ITWOM/itm's and ITWOM/itwom_client's
terrain inputs. The DP/planner, routing, and the other primitives (Evaluate/BatteryModel/Samband) aren't
built yet — see CLAUDE.md.
"""
