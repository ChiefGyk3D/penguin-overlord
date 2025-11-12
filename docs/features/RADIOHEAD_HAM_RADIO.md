# Radiohead - HAM Radio & Propagation System

## Overview

The Radiohead cog provides comprehensive HAM radio resources, including:
- **Real-time solar weather** and propagation conditions from NOAA
- **Physics-based propagation predictions** using ionospheric models
- **ARRL band plan** reference data
- **License class information** with privileges and power limits
- **Frequency lookup** for HAM bands and common services
- **HAM radio trivia** and educational content

---

## 🌞 Solar Weather & Propagation

### Commands

#### `!solar` or `/solar`
Get comprehensive solar weather report with physics-based band predictions.

**Features:**
- Live NOAA Space Weather data (updated continuously)
- Solar indices: SFI (Solar Flux Index), K-index, A-index
- Ionospheric parameters: foF2 (critical frequency), MUF (Maximum Usable Frequency)
- D-layer absorption percentage (time-of-day dependent)
- NOAA scales: R (Radio Blackout), S (Solar Radiation), G (Geomagnetic Storm)
- Band-by-band predictions for 10 HF/VHF bands (160m-6m)
- VHF/UHF conditions including aurora predictions
- Gray line enhancement detection
- Seasonal Sporadic-E predictions
- Operating recommendations based on current conditions

**Example Output:**
```
☀️ Solar Weather Report
Comprehensive propagation forecast • 2025-11-12 15:30 UTC

📊 Solar Indices
Solar Flux (SFI): 145
A-index: 8
K-index: 2
foF2 (Critical Freq): 8.5 MHz
MUF (DX): 34.0 MHz
D-Layer Absorption: 35%

⚡ Radio Blackout: R0 (R0-R5) ✅ Clear
☀️ Solar Radiation: S0 (S0-S5) ✅ Normal
🧲 Geomagnetic Storm: G0 (G0-G5) ✅ Calm

📻 Band Conditions (HF/VHF)
160m: 🟡 Fair (daytime - poor)
80m: 🟢 Good (Reliable day/night workhorse)
40m: 🟢 Excellent (Most reliable all-around)
30m: 🟢 Good (CW/digital DX)
20m: 🟢 Excellent (worldwide DX)
17m: 🟢 Good (Underutilized gem)
15m: 🟢 Good (Solar-dependent DX)
12m: 🟡 Fair (Solar-dependent)
10m: 🟡 Fair (Magic band)
6m: 🟡 Fair (check for Es/aurora)

📡 VHF/UHF Conditions
2m: 🟡 Normal - Line of sight, tropospheric scatter
70cm: 🟡 Normal - Line of sight, repeaters, satellites

🌐 ISM/WiFi Band Effects (R3 Radio Blackout Active)
900MHz (33cm/ISM): 🟠 Possible interference - LoRa, Zigbee, ISM devices
2.4GHz (WiFi/BT): � Possible disruption - WiFi, Bluetooth may be affected
5GHz WiFi: �🟡 Minor impact possible
6GHz WiFi 6E: 🟡 Minimal impact expected
*This section only appears during R2+ radio blackout events*

💡 Operating Recommendations
✨ Great Conditions! 15m and 20m excellent for DX hunting.
✅ Good Conditions: Normal propagation expected.

🕐 Recommended Bands Now (Day, 15:00 UTC)
Best Now: 20m, 17m, 15m, 40m
Predictions based on MUF=34.0MHz, foF2=8.5MHz
```

#### `!propagation` or `/propagation`
Alias for `!solar` command.

#### `!drap` or `/drap`
Show D-Region Absorption Prediction (D-RAP) map from NOAA.

**Features:**
- Real-time HF absorption map (updated every 15 minutes)
- Global coverage showing MHz-level absorption
- Color-coded: Red = high absorption, Green/Blue = low absorption
- Critical for planning HF operations

**How to Read:**
- 🔴 **Red/Orange (5+ dB)**: HF signals significantly weakened - try lower bands (40m/80m)
- 🟡 **Yellow (2-5 dB)**: Moderate signal degradation
- 🟢 **Green/Blue (<2 dB)**: Good propagation conditions

**Example Output:**
```
📡 D-Region Absorption Prediction (D-RAP)
[Global absorption map showing current D-layer conditions]

Update Frequency: Every 15 minutes
Coverage: Global HF absorption
Tip: Red areas = try lower bands (40m/80m)
```

#### `!aurora` or `/aurora`
Show current auroral oval position and 30-minute forecast.

**Features:**
- Real-time auroral oval visualization
- 30-minute forecast prediction
- Updated every 5 minutes
- Essential for VHF/UHF aurora scatter operations

**For Radio Operators:**
- 🟢 Green aurora = VHF/UHF scatter possible (2m/70cm/6m)
- Point antennas **north** for best results
- Use **SSB or CW** (aurora distorts FM)
- Check K-index with `!solar` (K≥4 = good aurora conditions)

**Example Output:**
```
🌌 Aurora Oval - Current Conditions
[Auroral oval map showing current activity]

Forecast: 30-minute prediction
Update Frequency: Every 5 minutes
Radio Tip: Strong aurora = try 2m/6m SSB pointed north
```

#### `!radio_maps` or `/radio_maps`
Show comprehensive set of radio propagation maps.

**Features:**
- D-RAP absorption map (HF planning)
- Aurora forecast (VHF scatter)
- Solar X-ray flux chart (flare activity)
- All maps in one command

**What You Get:**
1. **D-RAP Map**: Plan HF operations, see absorption levels
2. **Aurora Map**: Plan VHF scatter, see oval position
3. **X-Ray Flux**: Understand recent flare activity
4. **Summary Guide**: How to interpret the maps

**Use Cases:**
- Quick visual check of all propagation factors
- Planning DXpeditions or contests
- Understanding sudden propagation changes
- Educational demonstrations

**Example Output:**
```
📡 Radio Propagation Maps
[D-RAP global absorption map]
[Aurora oval forecast map]
[Solar X-ray flux 6-hour chart]

📊 How to Use These Maps
• D-RAP: Red = HF difficult, Green = HF excellent
• Aurora: Point 2m/6m north during activity
• X-Ray: M/X flares = expect HF blackouts
```

---

## 📻 Propagation Physics Engine

### How It Works

The solar/propagation system uses **ionospheric physics** instead of arbitrary thresholds to predict band conditions.

#### 1. Critical Frequency (foF2) Calculation
- Estimated from Solar Flux Index using empirical relationship
- Solar minimum (SFI~70): foF2 ≈ 4-5 MHz
- Solar maximum (SFI~200): foF2 ≈ 10-12 MHz
- Formula: `foF2 = 7.0 × sqrt(SFI/100)`

#### 2. Maximum Usable Frequency (MUF)
- Calculated for typical DX distance (3000km)
- Distance-dependent multipliers:
  - Short paths (<500km): `MUF = foF2 × 3.0` (NVIS)
  - Medium (500-2000km): `MUF = foF2 × 3.5`
  - Long (2000-4000km): `MUF = foF2 × 4.0`
  - Very long (>4000km): `MUF = foF2 × 4.5`
- Optimal operating frequency: **85% of MUF**

#### 3. D-Layer Absorption
- Varies with solar zenith angle (UTC hour-based model)
- Peak absorption at solar noon: 50-70%
- Minimal at night: ~5%
- Scales with Solar Flux Index
- R-scale events add +20% per level (R1-R5)
- Lower frequencies affected more than higher

#### 4. Gray Line Enhancement
- Detected during sunrise/sunset periods
- Morning: 05:00-07:00 UTC
- Evening: 17:00-19:00 UTC
- Adds +20% propagation enhancement for HF bands
- D-layer minimal while F-layer remains ionized

#### 5. K-Index Geomagnetic Impact
- Frequency-dependent effects:
  - **15m+**: 15% impact per K-point
  - **20m**: 12% impact per K-point
  - **40m/30m**: 8% impact per K-point
  - **80m/160m**: 5% impact per K-point
- Higher bands more affected by geomagnetic storms

#### 6. Seasonal Factors
- **Winter (Dec-Feb)**: F2-layer +15% (winter anomaly), Es 10%
- **Equinox (Mar-Apr, Sep-Oct)**: F2-layer +10%, Es 40%
- **Summer (May-Aug)**: F2-layer -10%, Es 80% probability
- **Fall (Nov)**: F2-layer normal, Es 30%
- Sporadic-E enhancement for 10m/6m during summer

#### 7. ISM/WiFi Band Effects (NEW in v2.0)

**Context-Aware Display**: This section **only appears** during R2+ (Moderate or stronger) radio blackout events, keeping the output clean 98% of the time.

**When Active (R2+ Events):**
- **900 MHz (33cm/ISM)**: LoRa, Zigbee, ISM devices may experience interference
- **2.4 GHz**: WiFi, Bluetooth, Zigbee may be disrupted
- **5 GHz**: Minor impact possible during severe events
- **6 GHz (WiFi 6E)**: Minimal impact even during major events

**Why This Matters:**
- X-class solar flares can cause ionospheric disturbances affecting UHF/SHF bands
- Infrastructure effects (power grid fluctuations) during G4/G5 storms
- Helps IT admins, IoT developers, and security researchers understand RF disruptions
- Makes solar alerts actionable: "WiFi acting weird? Check if solar flare is happening!"

**Severity Levels:**
- **R2 (Moderate)**: 🟡 Monitor for issues
- **R3 (Strong)**: 🟠 Possible disruption
- **R4-R5 (Severe/Extreme)**: 🔴 Likely disruption

**Educational Value:**
Shows that solar storms affect more than just HF radio - your WiFi, smart home devices, and IoT networks can also be impacted during major solar events.

### Band Quality Scoring

Each band receives a quality score (0.0-1.0) based on:

1. **Frequency vs MUF/foF2 relationship**
   - Above MUF: Closed (0.0)
   - 85%-100% MUF: Marginal (0.5)
   - Between foF2 and 85% MUF: Excellent (1.0)
   - Below foF2: Absorption-dependent (0.7 - absorption)

2. **D-layer absorption penalty** (lower frequencies penalized more)
3. **K-index geomagnetic impact** (higher bands penalized more)
4. **Gray line enhancement** (+20% for HF)
5. **Sporadic-E enhancement** (summer 10m/6m +30%)

**Quality Levels:**
- 🟢 **Excellent**: Score ≥ 0.75
- 🟢 **Good**: Score ≥ 0.55
- 🟡 **Fair**: Score ≥ 0.35
- 🟠 **Poor**: Score ≥ 0.15
- 🔴 **Closed**: Score < 0.15

---

## 📚 Band Plan Reference

### `!bandplan` or `/bandplan`
View ARRL band plans with frequency allocations and mode designations.

**Usage:**
```
!bandplan              # Overview of all bands
!bandplan 20m          # Detailed 20m band plan
!bandplan 40m          # Detailed 40m band plan
```

**Bands Available:**
- 160m, 80m, 60m, 40m, 30m, 20m, 17m, 15m, 12m, 10m, 6m, 2m, 70cm

**Example:**
```
📻 ARRL Band Plan: 20 Meters

Range: 14.000 - 14.350 MHz

Frequency Segments:
14.000-14.070 → CW (CW DX window)
14.070-14.095 → Digital (RTTY, PSK31, FT8)
14.095-14.099 → Beacons
14.100-14.112 → CW/Digital (FT8, WSPR)
14.150-14.350 → Phone/CW (SSB, AM)

ℹ️ Usage Notes
🌍 Premier DX Band - Worldwide propagation during daylight
```

---

## 🎓 License Class Information

### `!ham_class <class>` or `/ham_class <class>`
Get detailed information about HAM radio license classes.

**Classes:**
- `technician` - Entry level license
- `general` - Intermediate license
- `extra` - Highest class license

**Information Provided:**
- Exam requirements (number of questions, passing score)
- **Band privileges** (frequency ranges and modes allowed)
- **Power limits** (HF, VHF, UHF)
- Upgrade paths

**Example:**
```
!ham_class general
```

Output shows:
- General class privileges on 160m-10m
- 1500W PEP power limit (HF)
- All modes authorized
- SSB privileges on HF bands
- Full 6m/2m/70cm privileges

---

## 🔍 Frequency Lookup

### `!frequency [service]` or `/frequency [service]`
Look up frequencies for HAM bands or common radio services.

**Without argument**: Random HAM band frequency and information

**With service name**: Specific service frequencies

**Services Available:**
- `lora` - LoRaWAN frequencies
- `wifi` - WiFi channel frequencies
- `bluetooth` - Bluetooth frequencies
- `zigbee` - ZigBee frequencies
- `ism` - ISM band frequencies
- `frs` - FRS (Family Radio Service)
- `gmrs` - GMRS (General Mobile Radio Service)
- `murs` - MURS (Multi-Use Radio Service)
- `cb` - Citizens Band
- `aprs` - APRS frequencies
- `rfid` - RFID frequencies
- `nfc` - NFC frequencies

**Examples:**
```
!frequency              # Random HAM band
!frequency lora         # LoRaWAN frequencies
!frequency wifi         # WiFi channels
!frequency gmrs         # GMRS channels
```

---

## 📡 Additional Commands

### `!hamnews`
Latest HAM radio news and updates from ARRL and QRZ.

### `!freqtrivia`
Random HAM radio frequency trivia and propagation facts.

**Categories:**
- History
- Propagation
- Space Weather
- Bands
- Modes
- Digital
- Antennas
- Satellites
- Operating
- Awards
- Safety
- Technology

---

## 🤖 Auto-Posting

The solar/propagation report can be automatically posted every 12 hours.

### Setup Commands (Admin only)

```bash
!solar_set_channel #ham-radio    # Set posting channel
!solar_enable                     # Enable auto-posting
!solar_disable                    # Disable auto-posting
!solar_status                     # Check configuration
```

### Environment Variables

```bash
SOLAR_POST_CHANNEL_ID=123456789012345678
```

**Posting Schedule:**
- Every 12 hours (00:00 UTC and 12:00 UTC)
- Automatic condition updates
- Physics-based predictions

---

## 🔬 Scientific Basis

The propagation predictions are based on:

1. **VOACAP** (Voice of America Coverage Analysis Program) principles
2. **ITU-R P.533** - HF propagation prediction method
3. **ARRL propagation studies** and empirical data
4. **NOAA Space Weather Prediction Center** live data
5. **Ionospheric physics** (Chapman layer theory)

### Data Sources

- **NOAA SWPC APIs**:
  - https://services.swpc.noaa.gov/products/noaa-scales.json
  - https://services.swpc.noaa.gov/json/f107_cm_flux.json
  - https://services.swpc.noaa.gov/json/planetary_k_index_1m.json

### Factors Considered

The system considers **9 propagation factors**:
1. Solar Flux Index (SFI)
2. K-index (geomagnetic activity)
3. R-scale (radio blackouts)
4. G-scale (geomagnetic storms)
5. UTC hour (time-of-day effects)
6. Month (seasonal variations)
7. Distance (path length)
8. foF2 (critical frequency)
9. MUF (maximum usable frequency)

---

## 💡 Usage Tips

### Best Times to Check

- **Before contesting** - Know which bands are open
- **Before DXpeditions** - Plan your frequencies
- **During solar events** - Monitor changing conditions
- **Gray line periods** - Catch enhanced propagation

### Interpreting Results

- **🟢 Excellent/Good**: Go make contacts!
- **🟡 Fair**: Try CW or digital modes
- **🟠 Poor**: Possible with patience and power
- **🔴 Closed**: Try WSPR for detection, but unlikely

### What to Do During:

**Solar Flares (R-scale events)**:
- Expect HF absorption, especially higher bands
- Lower bands (80m/40m) handle better
- Wait for D-layer to recover (nightfall)

**Geomagnetic Storms (G-scale events)**:
- Check 6m/2m for aurora propagation!
- Lower bands more stable
- Higher bands may have flutter/fading

**Low Solar Flux (SFI < 80)**:
- Focus on 40m and 80m
- 20m may still work during day
- 15m/10m likely closed

**High Solar Flux (SFI > 150)**:
- 10m "magic band" opens!
- 15m excellent for DX
- Try long path on 20m

---

## 🐛 Troubleshooting

### "Unable to fetch solar data"
- NOAA SWPC API may be temporarily down
- Try again in a few minutes
- Check https://www.swpc.noaa.gov/ status

### Predictions seem off
- System uses global average model
- Local conditions vary (terrain, antenna, power)
- Actual propagation depends on many factors
- Use predictions as guide, not gospel

### Auto-posting not working
- Verify channel permissions
- Check `!solar_status`
- Ensure bot has message send permissions
- Verify `SOLAR_POST_CHANNEL_ID` in environment

---

## 📖 Learning Resources

- **ARRL**: http://www.arrl.org/propagation
- **HamStudy**: https://hamstudy.org/
- **NOAA SWPC**: https://www.swpc.noaa.gov/
- **VOACAP**: https://www.voacap.com/
- **PSKReporter**: https://pskreporter.info/pskmap.html
- **DXMaps**: https://www.dxmaps.com/

---

## 📝 Version History

### v2.0 (November 2025) - Physics-Based Propagation
- ✨ Implemented ionospheric physics engine (7 helper functions)
- ✨ Added foF2/MUF calculations
- ✨ D-layer absorption modeling (solar zenith angle)
- ✨ Gray line detection and enhancement
- ✨ K-index frequency-dependent impact
- ✨ Seasonal F2-layer adjustments
- ✨ Sporadic-E probability modeling
- ✨ Continuous quality scoring (0.0-1.0)
- ✨ 10-band predictions with contextual information

### v1.0 - Initial Release
- Basic solar weather data from NOAA
- Simple band predictions
- ARRL band plans
- License class information
- Frequency lookup system
- HAM radio trivia

---

**73 de Penguin Overlord!** 📡🐧
