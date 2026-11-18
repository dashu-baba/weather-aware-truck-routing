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