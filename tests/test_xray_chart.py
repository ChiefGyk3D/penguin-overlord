#!/usr/bin/env python3
"""
Quick test script for GOES X-ray flux chart generation
"""

import asyncio
import sys
sys.path.insert(0, 'penguin-overlord')

async def test_chart():
    from utils.solar_embed import plot_xray_flux
    
    print("Fetching GOES X-ray data and generating chart...")
    
    for period in ['6h', '1d', '3d', '7d']:
        print(f"\nGenerating {period} chart...")
        buf = await plot_xray_flux(period)
        
        if buf:
            filename = f'test_xray_{period}.png'
            with open(filename, 'wb') as f:
                f.write(buf.getvalue())
            print(f"✅ Chart saved: {filename}")
        else:
            print(f"❌ Failed to generate {period} chart")

if __name__ == '__main__':
    asyncio.run(test_chart())
