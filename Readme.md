# Weather-Aware Truck Routing
 
**Weather-aware route planning for trucks.** 
Enter an origin, a destination, a departure time and a load weight. 
The app finds three truck routes, checks the forecast **at the moment the truck will reach each point**, 
scores the risk with load-aware rules, and recommends the safest route on an interactive weather map.

**Live app:** 

## Contents
 
1. [Features](./docs/Features.md)
2. [Rules](./docs/Rules.md)
3. [Tech stack](./docs/TechStack.md)
4. [Running locally](#running-locally)
5. [Credits](#credits)

## Running locally
 
**You'll need:** Python 3.12+, Node.js 20+, and a free TomTom API key from
[developer.tomtom.com](https://developer.tomtom.com). Open-Meteo needs no key.

## Credits
 
- Routing and geocoding © [TomTom](https://developer.tomtom.com)
- Weather data by [Open-Meteo.com](https://open-meteo.com) ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/))
- Basemap © [OpenFreeMap](https://openfreemap.org), map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- Map rendering: [MapLibre GL JS](https://maplibre.org)