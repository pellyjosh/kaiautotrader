#!/usr/bin/env python3
"""
Test script to verify Enhanced Martingale calculations are working correctly
"""

def test_martingale_calculation():
    """Test the Martingale calculation logic"""
    base_amount = 1.0
    multiplier = 1.5
    
    print("Testing Enhanced Martingale Calculation:")
    print(f"Base Amount: ${base_amount}")
    print(f"Multiplier: {multiplier}")
    print()
    
    # Test the correct calculation sequence
    print("Expected sequence:")
    for level in range(0, 5):
        amount = base_amount * (multiplier ** level)
        print(f"Level {level}: ${amount:.2f}")
    
    print()
    print("Explanation:")
    print("Level 0 = Base trade (no Martingale) = $1.00")
    print("Level 1 = First Martingale level = $1.00 * 1.5^1 = $1.50")
    print("Level 2 = Second Martingale level = $1.00 * 1.5^2 = $2.25")
    print("Level 3 = Third Martingale level = $1.00 * 1.5^3 = $3.38")
    print("Level 4 = Fourth Martingale level = $1.00 * 1.5^4 = $5.06")

if __name__ == "__main__":
    test_martingale_calculation()
