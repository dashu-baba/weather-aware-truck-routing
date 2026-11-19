## Features

### Available now

- **Three truck routes** from TomTom's truck routing. The planner uses the truck's gross weight (cargo plus
  tare) and makes sure the three routes are genuinely different. They are drawn on the map within seconds.
- **Place search.** Search a US place by name. The backend can also name any point on the map (reverse
  geocoding); picking a point on the map is coming next.
- **Weather at arrival time.** A checkpoint is placed every **10, 25 or 50 miles** (you choose). Each
  checkpoint gets the hourly forecast for the hour the truck is expected to be there, not the current weather.
- **Load-aware risk.** Wind, rain and snow are classified into Low, Moderate, High, Severe or No Travel,
  and heavy loads raise the risk in strong wind (see [the rules](./Rules.md)).
- **A recommendation with a reason.** Routes are ranked by No Travel, Severe and High miles, then
  average risk, then travel time. The UI shows which rule decided, e.g. *"fewer Severe miles"*. When every
  route has No Travel miles it says so, names the least bad route and suggests a later departure.
- **Live progress.** The weather is fetched in the background, so the routes appear first. A progress bar and a
  stage label ("Weather for 25-mile checkpoints") show the work, and an early pick appears as soon as the
  25-mile checkpoints are scored.
- **Route cards.** Each route shows distance, drive time, local arrival, No Travel, Severe and High miles,
  average and worst risk, and a bar of miles per risk level. Click a card to focus its route.
- **Risk on the map.** Each route is coloured by the risk between checkpoints, and clicking a checkpoint shows its
  ETA, wind, gust, rain, snow, forecast hour, risk level and the reasons behind it. Switching the checkpoint
  spacing or the focused route never calls the server.
- **API keys never reach the browser.** Every third-party call goes through the Django API.

### Coming next

- **Picking places on the map.** Click the map or drag a pin to set the origin and destination. A point outside
  the US is allowed but gets a warning.
- **Corridor weather map.** A heatmap clipped to a polygon around all three routes, with layers for **Risk, Wind,
  Gust, Rain and Snow**, a **0–48 hour forecast slider** with playback, and a readout of the value under the
  cursor. The backend already serves the heatmap data and the browser fetches it, but does not draw it yet.
- **Trucks on the timeline.** Each route's truck moves along its route as you drag the slider, so you can see it
  meeting the weather.

See [Assumptions](./Assumptions.md) for what the planner assumes and does not model.
