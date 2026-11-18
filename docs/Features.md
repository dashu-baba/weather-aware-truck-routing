## Features

- **Three truck routes** from TomTom's truck routing. The planner uses the truck's gross weight and
  makes sure the three routes are genuinely different.
- **Weather at arrival time.** A checkpoint is placed every **10, 25 or 50 miles** (you choose). Each
  checkpoint gets the hourly forecast for the hour the truck is expected to be there, not the current weather.
- **Load-aware risk.** Wind, rain and snow are classified into Low, Moderate, High, Severe or No Travel,
  and heavy loads raise the risk in strong wind (see [the rules](./Rules.md)).
- **A recommendation with a reason.** Routes are ranked by No Travel, Severe and High miles, then
  average risk, then travel time. The UI shows which rule decided, e.g. *"fewer Severe miles"*.
- **Corridor weather map.**
  - A smooth heatmap clipped to a polygon around all three routes.
  - Layers for **Risk, Wind, Gust, Rain and Snow**, each with a realistic or a risk-band palette.
  - A **0–48 hour forecast slider** with smooth playback.
  - **Animated wind particles.**
  - A readout of the value under the cursor.
- **Trucks on the timeline.** Each route's truck moves along its route as you drag the slider, so you
  can see it meeting the weather.
- **API keys never reach the browser.** Every third-party call goes through the Django API.