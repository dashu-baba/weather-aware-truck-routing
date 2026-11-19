## Risk rules and recommendation
 
| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |
 
**Load rules (applied to wind):**
- Wind ≥ 55 mph → **No Travel** for any load.
- Wind 45–54 mph with load > 30,000 lb → **No Travel**.
- Wind 35–44 mph with load > 40,000 lb → **Severe**.
**Checkpoint risk** = the worst of the three conditions after the load rules.
 
**Route ranking** compares in this order, and the first difference decides:
1. fewest **No Travel** miles;
2. fewest **Severe** miles;
3. fewest **High** miles;
4. lowest **average risk** (weighted by distance);
5. shortest **travel time**.

**How the numbers are applied**
- Wind means the **sustained** speed, not gusts.
- Weather is matched at the checkpoint's ETA, to the nearest forecast hour. A checkpoint with no forecast is scored Low
  and noted in the result's warnings.
- A checkpoint's risk covers the stretch before it, and miles and average risk are weighted by that distance.
- The ranges overlap at their edges. A value equal to a range's lower bound belongs to the higher level (wind 25 is
  Moderate), except No Travel: wind at least 55 is inclusive, while rain above 1.00 and snow above 3.0 are exclusive (rain
  1.00 is Severe, 1.01 is No Travel).

See [Assumptions](./Assumptions.md) for the rest, including what the rules do not cover (ice, fog, closures).