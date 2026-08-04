# Solution & KPI monetisation map

Purpose: turn the GeoVision IoT platform into revenue with the **cheapest credible entry point** —
without pretending the product is "a sensor".

> **The core correction:** you never sell a sensor. You sell a **solution/kit** — a sensor (or a
> few) **plus** the edge controller, power, enclosure, connectivity, optional control outputs,
> installation, and the recurring platform. The sensor is the wedge that proves the panel is
> accurate; the **kit + recurring monitoring** is the business.

Every sensor key below matches the platform's canonical registry
(`backend/app/iot/registry.py`), so anything here is already unit-validated and ingestible.
Prices are **illustrative USD** taken from the GeoVision catalogue drafts — localise to AOA/EUR
through the existing multi-currency catalogue, and confirm supplier/bulk pricing before quoting.

---

## 1. Anatomy of a GeoVision solution (what's actually in every sale)

```
[ Sensors ] → [ Edge controller ] → [ Power ] → [ Connectivity ] → [ GeoVision cloud ] → [ Dashboard / Mobile ]
                     │                                                                          │
                [ Enclosure + wiring + protection ]                                   [ Alerts · Reports · Analytics ]
                     │
             [ Control outputs (optional): relay · valve · pump · contactor ]
```

A deployment is a **stack**, not a part. This is why "agriculture is not just sensors": a field
node also needs solar power, a weather-resistant enclosure, long-range connectivity, a mast, and
often control valves for irrigation — plus the recurring platform on top.

### The universal "box" (base BOM, ~$500 pilot kit)

| Component | Role | Illustrative cost |
|---|---|---|
| Edge controller (ESP32 + I/O) | Reads sensors, buffers, signs, sends | $15 |
| Sensors (3–4, vertical-specific) | The measurement | $60–$120 |
| IP65/IP67 enclosure | Weatherproofing | $30 |
| Power supply + DC-DC + fuse/SPD | Safe power | $35 |
| Cables, glands, terminals, small parts | Clean, safe wiring | $40 |
| Connectivity (Wi-Fi/4G router + SIM, or LoRaWAN) | Internet | $50 |
| GeoVision dashboard | Software | **$0** (existing licence) |
| Assembly / soldering / test | Build labour | $70 |
| Installation materials (mounts, ties, labels) | Field install | $40 |
| Site transport / pilot visit | Getting there | $80 |
| Spare parts / reserve | Contingency | $60 |
| **Base kit total** | | **≈ $500** |

Add solar power, battery backup, extra sensors, or control outputs on top per vertical.

---

## 2. How each euro is earned (monetisation layers)

| Layer | Type | Illustrative price | What the client pays for |
|---|---|---|---|
| **Solution kit (hardware)** | One-off | kit cost + 25–60% | Full assembled, flashed, weatherproof node — not loose parts |
| Installation & commissioning | One-off service | $80–$300 / site | Mount, wire, provision, calibrate, assign to asset, first report |
| **Monitoring subscription** | **Recurring (MRR)** | **$30–$80 / site / mo** | Live panel, storage, history, standard alerts — *the compounding line* |
| Per-device add-on | Recurring | $3–$15 / device / mo | Extra nodes on the same site |
| Premium alerts | Recurring add-on | $2–$8 / device / mo | WhatsApp/SMS/Telegram beyond free log/email |
| **Control & automation** | Recurring add-on | $5–$20 / device / mo | Safe relay/valve/pump commands + rules (raises tier) |
| Compliance & reports | Recurring / per-report | $5–$30 / report | Branded PDF (uptime, min/max/avg, incidents) |
| Analytics / KPI pack | Recurring add-on | $10–$40 / site / mo | Aggregations, trends, benchmarking, recommendations |
| Calibration programme | Recurring service | $20–$80 / device / yr | Scheduled recalibration + certificate |
| **Drone services** | Per-job add-on | $250+/flight; project $1k–$5k | Aerial survey/inspection to close bigger projects |

The recurring **monitoring subscription per site** is what makes this a platform business; the kit
and install land the account, control/automation and analytics lift ARPU, drones win big projects.

---

## 3. Solution tiers & ROI (the quote ladder)

| Tier | Scope | Investment | Setup | Break-even | 12-mo ROI |
|---|---|---|---|---|---|
| **Simple monitoring** | 1 node, 3–4 sensors, alerts, reports | $300–$800 | 1–3 days | 2–3 clients | 80–250% |
| **Advanced monitoring** | multi-node/site, Tier-2 sensors, analytics | $800–$2,500 | 3–7 days | 3–5 clients | 100–300% |
| **Automation + control** | monitoring + safe valve/pump/relay control | $1,500–$5,000 | 7–20 days | 2–4 clients | 150–400% |
| **Full turnkey** | multi-site, roles, ERP, SLA, compliance | $5,000+ | 20–60 days | 1–3 projects | 200–500% |
| **Drone add-on** | survey/inspection layered on any tier | $1,000–$5,000 | 2–5 days | 3–6 jobs | 100–300% |

**Start-small strategy:** land on Simple monitoring (cheap, fast, live demo proves accuracy) →
add automation & control → layer drones to close bigger projects → scale across sites/industries.

---

## 4. Worked example — Agriculture is a *solution*, not a soil probe

### 4a. Full solution BOM (open-field / irrigation node)

| Layer | Item(s) | Why it's needed | Illustrative |
|---|---|---|---|
| Sensors | soil_moisture, soil_temperature, ph/electrical_conductivity, leaf wetness, rain gauge | Crop & irrigation decisions | $45–$160 |
| Weather | weather station (temp/humidity/wind/rain/solar, 7-in-1) | Frost/heat, ET, spray windows | $129–$160 |
| Water metering | flow meter (irrigation) | Water used vs applied | $30–$59 |
| Edge controller | ESP32 + I/O (or industrial gateway) | Read/buffer/sign/send | $15–$60 |
| **Power** | **solar panel + battery (field has no mains)** | Off-grid autonomy | $120–$300 |
| Connectivity | LoRaWAN or 4G (fields are far from Wi-Fi) | Range | $50+ |
| Enclosure + mast + wiring | IP65 box, pole, glands, SPD | Survive the field | $60–$120 |
| **Control outputs (upsell)** | solenoid **valve** + **pump** relay/contactor | Automated irrigation/fertigation | $60–$250 |
| Install & commissioning | mount, wire, provision, calibrate | Make it work on site | $80–$300 |
| **Recurring** | monitoring + agronomy analytics + alerts | The MRR | $30–$80 / site / mo |

So the "agriculture kit" is a **solar-powered field node with sensors + weather + water metering +
optional automated-irrigation control**, on a recurring platform — the soil probe is one line item.

### 4b. KPIs it sells
Soil-moisture time-in-range, irrigation events & water used (m³), rainfall-vs-irrigation, ET-based
scheduling, frost/heat alerts, pump run-hours, fertigation EC/pH in-range, yield-risk flags.

### 4c. Monetisation path
- **Land:** Simple monitoring node (soil + weather) — prove the panel matches the field. $300–$800 + $30–$80/mo.
- **Grow:** add EC/pH fertigation, flow metering, more nodes → Advanced + Analytics.
- **Automate (higher tier):** add valve/pump control for scheduled/threshold irrigation → Automation+Control $1,500–$5,000.
- **Close big:** drone crop survey/NDVI-style inspection as a per-project add-on.

---

## 5. Industry × solution-stack matrix

Which stack layers each vertical typically needs (beyond the always-on edge + enclosure + platform).
Legend: ● core · ○ common upsell · – rare

| Layer \ Industry | Agriculture | Water & Sanitation | Energy & Solar | Cold Chain | Facilities/Retail | Telecom/Remote | Industrial | Environment/Construction | Livestock | Fleet/Logistics |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Vertical sensors | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Solar + battery power | ● | ○ | ● | – | – | ● | ○ | ● | ● | ○ |
| Long-range conn. (LoRa/4G) | ● | ○ | ○ | – | – | ● | ○ | ● | ● | ● (4G) |
| Weather station | ● | ○ | ● | – | – | – | – | ● | ○ | – |
| Control outputs (valve/pump/relay) | ○→● | ● (pump) | ○ (genset/load) | ○ (compressor) | ○ (HVAC) | ○ | ● (machine) | – | ○ (gate/feed) | – |
| GPS / tracking | ○ | – | – | ○ (transit) | – | ○ | ○ | ● | ● (animals) | ● |
| Gas/air safety | ○ | – | – | – | ○ | – | ● | ● | ○ | – |
| Ruggedised/industrial edge | ○ | ○ | ● | ○ | – | ● | ● | ● | ○ | ● |

---

## 6. Industry × sensor matrix (the measurement layer)

Legend: ● core (sell first) · ○ optional upsell · – not typical

| Sensor \ Industry | Agriculture | Water | Energy | Cold Chain | Facilities | Telecom | Industrial | Environment | Livestock |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| temperature | ● | ○ | ○ | ● | ● | ● | ● | ○ | ● (barn) |
| humidity | ● | – | – | ● | ○ | ○ | ○ | ○ | ● |
| water_leak | ○ | ● | ○ | ● | ● | ○ | ● | – | ○ |
| tank_level | ● | ● | ○ (fuel) | – | ○ | ○ | ● | – | ● (trough) |
| door_contact | – | ○ | ○ | ● | ● | ● | ○ | – | ● (gate) |
| motion | – | – | – | ○ | ● | ● | ○ | ○ | ○ |
| voltage/current/power/energy | ○ | ○ | ● | ○ | ● | ● | ● | – | – |
| run_status | ● (pump) | ● (pump) | ● (genset) | ● (compressor) | ○ | ● | ● | – | ○ |
| flow | ● | ● | – | – | – | – | ○ | ○ | ○ |
| pressure | ○ | ● | ○ | – | ○ | – | ● | ○ | – |
| soil_moisture / soil_temperature | ● | – | – | – | – | – | – | ○ | – |
| ph / electrical_conductivity | ● (fertigation) | ● (quality) | – | – | – | – | ○ | ○ | ○ (water) |
| turbidity / dissolved_oxygen | ○ | ● | – | – | – | – | ○ | ○ | ○ |
| fuel_level | ○ | – | ● | – | – | ● | ○ | ○ | – |
| co2 / pm2_5 / voc / air_quality | ○ (greenhouse) | – | – | ○ | ○ | – | ○ | ● | ○ (barn) |
| vibration | – | ○ (pump) | ○ | ○ | – | – | ● | ○ | – |
| rainfall / wind / solar_irradiance | ● | ○ | ● | – | – | – | – | ● | ○ |
| GPS (lat/long) | ○ | ○ | ○ | ○ | – | ○ | ○ | ● | ● (animals) |
| tilt / crack_displacement | – | ● (dam/tank) | – | – | – | ● (tower) | ○ | ● | – |
| load / weight | ○ (feed/silo) | ○ | – | – | – | – | ● | ● | ● (feed/animal) |
| battery / signal | ● | ● | ● | ● | ● | ● | ● | ● | ● |

---

## 7. Industry × KPI matrix (what the panel sells)

| Industry | Headline KPIs | Recommended tier |
|---|---|---|
| **Agriculture** | soil-moisture time-in-range, water used, ET scheduling, frost/heat alerts, pump run-hours, fertigation EC/pH | Simple → Advanced+Analytics → Automation |
| **Water & Sanitation** | tank days-of-supply, pump run-hours/starts, flow m³/day, leak events, turbidity/pH in-limit, supply uptime | Advanced + Compliance |
| **Energy & Solar** | kWh in/out, peak demand, genset run-hours & fuel %, solar yield vs irradiance, outage count/duration | Advanced + Analytics |
| **Cold Chain / Pharma** | time-in-range %, excursion count/duration, MKT proxy, door-open events, compressor run-hours | Turnkey (compliance) |
| **Facilities & Retail** | energy $/site, after-hours power, occupancy/motion, door events, leak incidents | Advanced |
| **Telecom / Remote** | site availability %, genset run-hours & fuel %, battery health, intrusion events, tower tilt | Turnkey (SLA) |
| **Industrial / Mfg** | machine run-hours & duty cycle, energy/shift, vibration trend, overload events, downtime minutes | Advanced + Automation |
| **Environment / Construction** | AQI/PM2.5/CO₂ exposure hours, noise dose, structural tilt & crack trend, weather feed | Advanced + Compliance |
| **Livestock** | animal location/geofence, activity/inactivity, body temp, barn climate in-range, trough level, feed-bin level | Simple → Advanced |
| **Fleet / Logistics** | location & geofence, cargo/reefer temperature, door events, shock, battery/uptime | Advanced |

---

## 8. KPI catalogue (definition → source channels)

| KPI | Definition | Source channels |
|---|---|---|
| Uptime % | online time / period | device status, `signal` |
| Data completeness % | received / expected samples | telemetry cadence |
| Time-in-range % | samples within [min,max] / total | any numeric channel + rule bounds |
| Excursion count/duration | contiguous out-of-range episodes | `temperature`, `humidity`, … |
| Run-hours / starts | integral of `run_status`; rising edges | `run_status` |
| Days-of-supply | `tank_level` ÷ draw rate | `tank_level`, `flow` |
| Water used | ∫`flow` over period | `flow` |
| Energy in/out | Δ`energy` (or ∫`power`) | `energy`, `power` |
| Peak demand | max `power` in window | `power` |
| Fuel use / theft flag | Δ`fuel_level` vs run-hours | `fuel_level`, `run_status` |
| Solar yield ratio | `energy` ÷ `solar_irradiance` | `solar_irradiance`, `energy` |
| Vibration trend | rolling RMS of `vibration` | `vibration` |
| Exposure hours | time above AQI/noise limit | `pm2_5`, `co2`, `noise` |
| Structural drift | cumulative Δ`tilt`/`crack_displacement` | `tilt`, `crack_displacement` |
| Geofence breach | position outside boundary | `latitude`, `longitude` |
| Incident count / MTTA / MTTR | alerts opened; ack/resolve latency | alert lifecycle |

All are derivable from existing `telemetry_readings`, `telemetry_aggregates` and `iot_alerts` —
no schema change needed to start selling them.

---

## 9. Packaging summary

| Plan | Kit | Sensors | Control | Alerts | Reports | Target |
|---|---|---|---|---|---|---|
| **Simple "prove-it"** | base box, 1 node | Tier-1 core | – | log + email | monthly PDF | land the account |
| **Advanced** | multi-node/site, solar/LoRa as needed | + Tier-2 vertical | – | + WhatsApp/SMS | weekly PDF + CSV/API | SMB rollout |
| **Automation + control** | + relays/valves/pumps | full vertical | ● safe low-voltage | escalation | full suite | operations |
| **Full turnkey** | multi-site, industrial edge | unlimited | ● + rules | full multi-channel | compliance | utilities/pharma/telecom |
| **+ Drone** | any of the above | — | — | — | survey/inspection | close bigger projects |

**Golden rule:** quote a **complete working node** and a **recurring per-site subscription** — never
a bag of sensors. Land cheap, let the live panel prove accuracy, then climb the tier ladder.
