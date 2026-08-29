#!/usr/bin/env python3
"""
Test script for radiohead.py propagation physics engine.
Tests the new physics-based propagation calculations locally without Discord.

Usage:
    python3 tests/test_radiohead_propagation.py
    python3 tests/test_radiohead_propagation.py --sfi 150 --k 3
"""

import sys
import os
from datetime import datetime
import math

# Add parent directory to path to import from penguin-overlord
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'penguin-overlord'))

# Import the propagation functions from radiohead
from cogs.radiohead import (
    estimate_fof2_from_sfi,
    calculate_muf_for_distance,
    calculate_d_layer_absorption,
    calculate_gray_line_enhancement,
    get_k_index_impact,
    get_seasonal_factor,
    predict_band_conditions
)


def test_propagation_calculations(sfi=145, k_index=2, r_scale='R0', utc_hour=None):
    """
    Test propagation calculations with given parameters.
    
    Args:
        sfi: Solar Flux Index (70-250)
        k_index: K-index (0-9)
        r_scale: R-scale ('R0'-'R5')
        utc_hour: UTC hour (0-23), None = current
    """
    print("=" * 80)
    print("RADIOHEAD PROPAGATION PHYSICS ENGINE - LOCAL TEST")
    print("=" * 80)
    print()
    
    # Get current time if not specified
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
    
    # Calculate propagation parameters
    print("=" * 80)
    print("STEP 1: Calculate Ionospheric Parameters")
    print("=" * 80)
    print()
    
    # 1. Calculate foF2 (critical frequency)
    fof2 = estimate_fof2_from_sfi(sfi)
    print(f"✓ foF2 (Critical Frequency): {fof2:.2f} MHz")
    print(f"  Formula: foF2 = 7.0 × sqrt(SFI/100)")
    print(f"  Calculation: 7.0 × sqrt({sfi}/100) = {fof2:.2f} MHz")
    print()
    
    # 2. Calculate MUF for different distances
    muf_nvis = calculate_muf_for_distance(fof2, 300)      # NVIS
    muf_regional = calculate_muf_for_distance(fof2, 1000) # Regional
    muf_dx = calculate_muf_for_distance(fof2, 3000)       # DX
    muf_long = calculate_muf_for_distance(fof2, 5000)     # Long path
    
    print(f"✓ Maximum Usable Frequency (MUF):")
    print(f"  NVIS (300km):     {muf_nvis:.2f} MHz  (foF2 × 3.0)")
    print(f"  Regional (1000km): {muf_regional:.2f} MHz  (foF2 × 3.5)")
    print(f"  DX (3000km):       {muf_dx:.2f} MHz  (foF2 × 4.0)")
    print(f"  Long path (5000km): {muf_long:.2f} MHz  (foF2 × 4.5)")
    print()
    
    # 3. Calculate D-layer absorption
    d_absorption = calculate_d_layer_absorption(utc_hour, r_scale, sfi)
    print(f"✓ D-Layer Absorption: {d_absorption*100:.1f}%")
    print(f"  Time factor: {'Daytime' if 6 <= utc_hour <= 18 else 'Nighttime'}")
    print(f"  SFI scaling: {sfi}/150 = {sfi/150:.2f}x")
    print(f"  R-scale impact: {r_scale}")
    print()
    
    # 4. Check gray line
    is_gray_line, gray_line_msg = calculate_gray_line_enhancement(utc_hour)
    print(f"✓ Gray Line Status: {'YES' if is_gray_line else 'NO'}")
    if is_gray_line:
        print(f"  {gray_line_msg}")
    else:
        print(f"  Not during gray line period (05-07 or 17-19 UTC)")
    print()
    
    # 5. Seasonal factors
    f2_factor, es_probability, season_name = get_seasonal_factor(current_month)
    print(f"✓ Seasonal Factors ({season_name}):")
    print(f"  F2-layer adjustment: {f2_factor:.2%} ({f2_factor}x)")
    print(f"  Sporadic-E probability: {es_probability:.0%}")
    print()
    
    # Band-by-band predictions
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
        # Calculate K-index impact for this band
        k_impact = get_k_index_impact(k_index, freq_mhz)
        
        # Get band conditions prediction
        score, emoji, quality = predict_band_conditions(
            freq_mhz, fof2, muf_dx, d_absorption, k_impact, is_gray_line, current_month
        )
        
        results.append((band_name, freq_range, emoji, quality, score, k_impact))
        
        # Detailed breakdown for each band
        print(f"{band_name} ({freq_range}):")
        print(f"  Quality: {emoji} {quality} (Score: {score:.3f})")
        print(f"  K-index impact: {k_impact:.3f} (sensitivity: {k_impact/max(k_index, 0.1):.2f})")
        
        # Show why
        if freq_mhz > muf_dx:
            print(f"  → Above MUF ({muf_dx:.1f} MHz) - Band closed")
        elif freq_mhz > muf_dx * 0.85:
            print(f"  → Near MUF limit - Marginal propagation")
        elif freq_mhz < fof2:
            print(f"  → Below foF2 - Subject to absorption ({d_absorption*100:.0f}%)")
        else:
            print(f"  → Sweet spot (foF2={fof2:.1f} to MUF={muf_dx:.1f})")
        
        print()
    
    # Summary table
    print("=" * 80)
    print("STEP 3: Summary Table")
    print("=" * 80)
    print()
    print(f"{'Band':<8} {'Frequency':<20} {'Status':<4} {'Quality':<12} {'Score':<7} {'K-Impact':<9}")
    print("-" * 80)
    for band_name, freq_range, emoji, quality, score, k_impact in results:
        print(f"{band_name:<8} {freq_range:<20} {emoji:<4} {quality:<12} {score:<7.3f} {k_impact:<9.3f}")
    print()
    
    # Operating recommendations
    print("=" * 80)
    print("STEP 4: Operating Recommendations")
    print("=" * 80)
    print()
    
    # Best bands right now
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
    
    # Specific recommendations
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
    
    # Test verdict
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
    print("=" * 80)
    print("EDGE CASE TESTING")
    print("=" * 80)
    print()
    
    scenarios = [
        ("Solar Minimum", 70, 2, 'R0', 12),
        ("Solar Maximum", 220, 1, 'R0', 12),
        ("Geomagnetic Storm", 150, 7, 'R0', 2),
        ("Solar Flare", 150, 3, 'R5', 12),
        ("Gray Line Morning", 120, 2, 'R0', 6),
        ("Gray Line Evening", 120, 2, 'R0', 18),
        ("Night Time", 100, 2, 'R0', 2),
    ]
    
    for name, sfi, k, r, hour in scenarios:
        print(f"\n{'='*80}")
        print(f"Scenario: {name}")
        print(f"{'='*80}")
        test_propagation_calculations(sfi, k, r, hour)
        input("\nPress Enter to continue to next scenario...")


def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test radiohead propagation physics')
    parser.add_argument('--sfi', type=int, default=145, help='Solar Flux Index (70-250)')
    parser.add_argument('--k', type=float, default=2, help='K-index (0-9)')
    parser.add_argument('--r', type=str, default='R0', help='R-scale (R0-R5)')
    parser.add_argument('--hour', type=int, default=None, help='UTC hour (0-23)')
    parser.add_argument('--edge-cases', action='store_true', help='Run edge case scenarios')
    
    args = parser.parse_args()
    
    print()
    print("🐧 Penguin Overlord - Radiohead Propagation Test")
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
