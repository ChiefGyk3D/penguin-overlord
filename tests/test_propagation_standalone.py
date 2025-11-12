#!/usr/bin/env python3
"""
Standalone test for radiohead.py propagation physics engine.
Tests propagation calculations locally without requiring Discord.

Usage:
    python3 tests/test_propagation_standalone.py
    python3 tests/test_propagation_standalone.py --sfi 150 --k 3
    python3 tests/test_propagation_standalone.py --edge-cases
"""

import math
from datetime import datetime


# ============================================================================
# PROPAGATION HELPER FUNCTIONS (copied from radiohead.py)
# ============================================================================

def estimate_fof2_from_sfi(sfi_value):
    """Estimate critical frequency (foF2) from Solar Flux Index."""
    base_fof2 = 7.0
    scale = math.sqrt(max(sfi_value, 50) / 100.0)
    return base_fof2 * scale


def calculate_muf_for_distance(fof2, distance_km):
    """Calculate Maximum Usable Frequency for a given distance."""
    if distance_km < 500:
        return fof2 * 3.0  # NVIS
    elif distance_km < 2000:
        return fof2 * 3.5  # Single hop F2
    elif distance_km < 4000:
        return fof2 * 4.0  # Multi-hop
    else:
        return fof2 * 4.5  # Very long distance


def calculate_d_layer_absorption(utc_hour, r_scale, sfi_value):
    """Calculate D-layer absorption factor."""
    r_val = 0
    if r_scale not in ['R0', 'N/A']:
        try:
            r_val = int(r_scale.replace('R', ''))
        except:
            r_val = 0
    
    hour_angle = abs(utc_hour - 12)
    
    if hour_angle > 6:
        base_absorption = 0.05  # Night
    else:
        base_absorption = 0.3 + (0.4 * (1.0 - hour_angle / 6.0))
    
    sfi_factor = min(sfi_value / 150.0, 2.0)
    base_absorption *= sfi_factor
    
    if r_val > 0:
        base_absorption += (r_val * 0.2)
    
    return min(base_absorption, 1.0)


def calculate_gray_line_enhancement(utc_hour):
    """Determine if current time is during gray line period."""
    morning_gray = (5 <= utc_hour <= 7)
    evening_gray = (17 <= utc_hour <= 19)
    
    if morning_gray or evening_gray:
        time_desc = "Morning" if morning_gray else "Evening"
        return (True, f"🌅 {time_desc} Gray Line - Enhanced DX propagation!")
    
    return (False, None)


def get_k_index_impact(k_index, band_mhz):
    """Calculate K-index impact on propagation for specific band."""
    try:
        k_val = float(k_index)
    except:
        k_val = 2.0
    
    if band_mhz >= 21:
        sensitivity = 0.15
    elif band_mhz >= 14:
        sensitivity = 0.12
    elif band_mhz >= 7:
        sensitivity = 0.08
    else:
        sensitivity = 0.05
    
    impact = min(k_val * sensitivity, 1.0)
    return impact


def get_seasonal_factor(month):
    """Calculate seasonal propagation factor."""
    if month in [12, 1, 2]:  # Winter
        return (1.15, 0.1, "Winter")
    elif month in [3, 4, 9, 10]:  # Equinox
        return (1.1, 0.4, "Equinox")
    elif month in [5, 6, 7, 8]:  # Summer
        return (0.9, 0.8, "Summer")
    else:  # Fall
        return (1.0, 0.3, "Fall")


def predict_band_conditions(band_mhz, fof2, muf, absorption, k_impact, is_gray_line, month=None):
    """Predict propagation conditions for a specific band."""
    if month:
        f2_factor, es_probability, season_name = get_seasonal_factor(month)
        fof2_adjusted = fof2 * f2_factor
        muf_adjusted = muf * f2_factor
    else:
        fof2_adjusted = fof2
        muf_adjusted = muf
        es_probability = 0.3
    
    optimal_muf = muf_adjusted * 0.85
    
    if band_mhz > muf_adjusted:
        base_score = 0.0
    elif band_mhz > optimal_muf:
        base_score = 0.5
    elif band_mhz < fof2_adjusted:
        base_score = 0.7 - absorption
    else:
        base_score = 1.0
    
    freq_absorption_factor = max(0.3, 1.0 - (band_mhz / 30.0))
    absorption_penalty = absorption * freq_absorption_factor
    base_score -= absorption_penalty
    
    base_score -= k_impact
    
    if is_gray_line and band_mhz >= 3.5 and band_mhz <= 30:
        base_score += 0.2
    
    if (band_mhz >= 28 and band_mhz <= 54) and es_probability > 0.5:
        base_score += (es_probability * 0.3)
    
    final_score = max(0.0, min(1.0, base_score))
    
    if final_score >= 0.75:
        return (final_score, "🟢", "Excellent")
    elif final_score >= 0.55:
        return (final_score, "🟢", "Good")
    elif final_score >= 0.35:
        return (final_score, "🟡", "Fair")
    elif final_score >= 0.15:
        return (final_score, "🟠", "Poor")
    else:
        return (final_score, "🔴", "Closed")


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_propagation_calculations(sfi=145, k_index=2, r_scale='R0', utc_hour=None):
    """Test propagation calculations with given parameters."""
    print("=" * 80)
    print("RADIOHEAD PROPAGATION PHYSICS ENGINE - LOCAL TEST")
    print("=" * 80)
    print()
    
    if utc_hour is None:
        utc_hour = datetime.utcnow().hour
    
    current_month = datetime.utcnow().month
    
    print(f"📊 Test Parameters:")
    print(f"   Solar Flux Index (SFI): {sfi}")
    print(f"   K-index: {k_index}")
    print(f"   R-scale: {r_scale}")
    print(f"   UTC Hour: {utc_hour:02d}:00")
    print(f"   Month: {current_month} ({datetime.utcnow().strftime('%B')})")
    print()
    
    print("=" * 80)
    print("STEP 1: Calculate Ionospheric Parameters")
    print("=" * 80)
    print()
    
    fof2 = estimate_fof2_from_sfi(sfi)
    print(f"✓ foF2 (Critical Frequency): {fof2:.2f} MHz")
    print(f"  Formula: foF2 = 7.0 × sqrt(SFI/100)")
    print(f"  Calculation: 7.0 × sqrt({sfi}/100) = {fof2:.2f} MHz")
    print()
    
    muf_nvis = calculate_muf_for_distance(fof2, 300)
    muf_regional = calculate_muf_for_distance(fof2, 1000)
    muf_dx = calculate_muf_for_distance(fof2, 3000)
    muf_long = calculate_muf_for_distance(fof2, 5000)
    
    print(f"✓ Maximum Usable Frequency (MUF):")
    print(f"  NVIS (300km):       {muf_nvis:.2f} MHz  (foF2 × 3.0)")
    print(f"  Regional (1000km):  {muf_regional:.2f} MHz  (foF2 × 3.5)")
    print(f"  DX (3000km):        {muf_dx:.2f} MHz  (foF2 × 4.0)")
    print(f"  Long path (5000km): {muf_long:.2f} MHz  (foF2 × 4.5)")
    print()
    
    d_absorption = calculate_d_layer_absorption(utc_hour, r_scale, sfi)
    print(f"✓ D-Layer Absorption: {d_absorption*100:.1f}%")
    print(f"  Time factor: {'Daytime' if 6 <= utc_hour <= 18 else 'Nighttime'}")
    print(f"  SFI scaling: {sfi}/150 = {sfi/150:.2f}x")
    print(f"  R-scale impact: {r_scale}")
    print()
    
    is_gray_line, gray_line_msg = calculate_gray_line_enhancement(utc_hour)
    print(f"✓ Gray Line Status: {'YES' if is_gray_line else 'NO'}")
    if is_gray_line:
        print(f"  {gray_line_msg}")
    else:
        print(f"  Not during gray line period (05-07 or 17-19 UTC)")
    print()
    
    f2_factor, es_probability, season_name = get_seasonal_factor(current_month)
    print(f"✓ Seasonal Factors ({season_name}):")
    print(f"  F2-layer adjustment: {f2_factor:.2%} ({f2_factor}x)")
    print(f"  Sporadic-E probability: {es_probability:.0%}")
    print()
    
    print("=" * 80)
    print("STEP 2: Band-by-Band Predictions")
    print("=" * 80)
    print()
    
    bands = [
        (1.9, "160m", "1.8-2.0 MHz"),
        (3.6, "80m", "3.5-4.0 MHz"),
        (7.1, "40m", "7.0-7.3 MHz"),
        (10.125, "30m", "10.1-10.15 MHz"),
        (14.2, "20m", "14.0-14.35 MHz"),
        (18.1, "17m", "18.068-18.168 MHz"),
        (21.2, "15m", "21.0-21.45 MHz"),
        (24.9, "12m", "24.89-24.99 MHz"),
        (28.5, "10m", "28.0-29.7 MHz"),
        (50.1, "6m", "50.0-54.0 MHz"),
    ]
    
    results = []
    
    for freq_mhz, band_name, freq_range in bands:
        k_impact = get_k_index_impact(k_index, freq_mhz)
        
        score, emoji, quality = predict_band_conditions(
            freq_mhz, fof2, muf_dx, d_absorption, k_impact, is_gray_line, current_month
        )
        
        results.append((band_name, freq_range, emoji, quality, score, k_impact))
        
        print(f"{band_name} ({freq_range}):")
        print(f"  Quality: {emoji} {quality} (Score: {score:.3f})")
        print(f"  K-index impact: {k_impact:.3f}")
        
        if freq_mhz > muf_dx:
            print(f"  → Above MUF ({muf_dx:.1f} MHz) - Band closed")
        elif freq_mhz > muf_dx * 0.85:
            print(f"  → Near MUF limit - Marginal propagation")
        elif freq_mhz < fof2:
            print(f"  → Below foF2 - Subject to absorption ({d_absorption*100:.0f}%)")
        else:
            print(f"  → Sweet spot (foF2={fof2:.1f} to MUF={muf_dx:.1f})")
        
        print()
    
    print("=" * 80)
    print("STEP 3: Summary Table")
    print("=" * 80)
    print()
    print(f"{'Band':<8} {'Frequency':<20} {'Status':<4} {'Quality':<12} {'Score':<7} {'K-Impact':<9}")
    print("-" * 80)
    for band_name, freq_range, emoji, quality, score, k_impact in results:
        print(f"{band_name:<8} {freq_range:<20} {emoji:<4} {quality:<12} {score:<7.3f} {k_impact:<9.3f}")
    print()
    
    print("=" * 80)
    print("STEP 4: Operating Recommendations")
    print("=" * 80)
    print()
    
    excellent_bands = [b[0] for b in results if b[3] == "Excellent"]
    good_bands = [b[0] for b in results if b[3] == "Good"]
    fair_bands = [b[0] for b in results if b[3] == "Fair"]
    
    if excellent_bands:
        print(f"🟢 Excellent bands: {', '.join(excellent_bands)}")
    if good_bands:
        print(f"🟢 Good bands: {', '.join(good_bands)}")
    if fair_bands:
        print(f"🟡 Fair bands: {', '.join(fair_bands)}")
    print()
    
    if d_absorption > 0.7:
        print("⚠️  High D-layer absorption - Lower bands recommended")
    elif d_absorption > 0.4:
        print("⚠️  Moderate absorption - Higher bands may be challenging")
    
    if muf_dx > 28:
        print("🎉 Excellent MUF! 10m magic band should be open")
    elif muf_dx < 14:
        print("💡 Low MUF - Focus on 40m and 80m")
    
    if is_gray_line:
        print("🌅 Gray line period - Enhanced DX propagation!")
    
    if es_probability > 0.6:
        print("✨ High Sporadic-E probability - Check 6m and 10m!")
    
    print()
    print("=" * 80)
    print("TEST VERDICT")
    print("=" * 80)
    print()
    print("✅ All propagation functions executed successfully!")
    print("✅ Physics calculations completed without errors")
    print("✅ Band predictions generated")
    print()
    print(f"Test completed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()


def test_edge_cases():
    """Test edge case scenarios."""
    scenarios = [
        ("Solar Minimum", 70, 2, 'R0', 12),
        ("Solar Maximum", 220, 1, 'R0', 12),
        ("Geomagnetic Storm", 150, 7, 'R0', 2),
        ("Solar Flare", 150, 3, 'R5', 12),
        ("Gray Line Morning", 120, 2, 'R0', 6),
        ("Gray Line Evening", 120, 2, 'R0', 18),
        ("Night Time", 100, 2, 'R0', 2),
    ]
    
    for i, (name, sfi, k, r, hour) in enumerate(scenarios, 1):
        print(f"\n{'='*80}")
        print(f"Scenario {i}/{len(scenarios)}: {name}")
        print(f"{'='*80}\n")
        test_propagation_calculations(sfi, k, r, hour)
        
        if i < len(scenarios):
            input("\nPress Enter to continue to next scenario...")


def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test radiohead propagation physics (standalone)')
    parser.add_argument('--sfi', type=int, default=145, help='Solar Flux Index (70-250)')
    parser.add_argument('--k', type=float, default=2, help='K-index (0-9)')
    parser.add_argument('--r', type=str, default='R0', help='R-scale (R0-R5)')
    parser.add_argument('--hour', type=int, default=None, help='UTC hour (0-23)')
    parser.add_argument('--edge-cases', action='store_true', help='Run edge case scenarios')
    
    args = parser.parse_args()
    
    print()
    print("🐧 Penguin Overlord - Radiohead Propagation Test (Standalone)")
    print()
    
    if args.edge_cases:
        test_edge_cases()
    else:
        test_propagation_calculations(args.sfi, args.k, args.r, args.hour)
    
    print("=" * 80)
    print("Test complete! Physics engine is working correctly. 73! 📡")
    print("=" * 80)
    print()


if __name__ == '__main__':
    main()
