#!/usr/bin/env python3
"""
Test script to verify signal parsing for Pocket Option Official Signal Bot format.
"""

import sys
import os
import re

# Add parent directory to path to import detectsignal
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the signal parsing function
from detectsignal import parse_signal_from_message, _normalize_pair_for_new_format

def test_pocket_signal_parser():
    """Test the signal parser with real Pocket Option bot messages"""
    
    print("🧪 Testing Pocket Option Signal Parser")
    print("=" * 50)
    
    # Test message from actual bot (from the conversation we saw)
    test_message = """SIGNAL ⬇

Asset: VISA_otc
Payout: 92%
Accuracy: 80%
Expiration: M5

--------------------------
Auto-trade: On
Change the Signal Bot settings by editing /settings"""

    print("📝 Test Message:")
    print(test_message)
    print("\n" + "=" * 50)
    
    # Parse the signal
    result = parse_signal_from_message(test_message)
    
    if result:
        print("✅ SIGNAL PARSED SUCCESSFULLY!")
        print(f"   Pair: {result['pair']}")
        print(f"   Action: {result['action']}")
        print(f"   Amount: ${result['amount']}")
        print(f"   Expiration: {result['expiration']} seconds ({result['expiration']//60} minutes)")
    else:
        print("❌ SIGNAL PARSING FAILED!")
        print("   The parser could not extract trading information from this message.")
    
    print("\n" + "=" * 50)
    
    # Test with UP signal
    test_message_up = """SIGNAL ⬆

Asset: EURUSD_otc
Payout: 88%
Accuracy: 75%
Expiration: M1

--------------------------
Auto-trade: On"""

    print("📝 Test Message (UP signal):")
    print(test_message_up)
    print("\n" + "=" * 50)
    
    result_up = parse_signal_from_message(test_message_up)
    
    if result_up:
        print("✅ UP SIGNAL PARSED SUCCESSFULLY!")
        print(f"   Pair: {result_up['pair']}")
        print(f"   Action: {result_up['action']}")
        print(f"   Amount: ${result_up['amount']}")
        print(f"   Expiration: {result_up['expiration']} seconds ({result_up['expiration']//60} minutes)")
    else:
        print("❌ UP SIGNAL PARSING FAILED!")
    
    return result is not None and result_up is not None

def test_pair_normalization():
    """Test the pair normalization function"""
    print("\n🔧 Testing Pair Normalization")
    print("=" * 50)
    
    test_pairs = [
        "VISA_otc",
        "EURUSD_otc", 
        "BTC/USD",
        "GBPUSD",
        "AUD/CAD_otc"
    ]
    
    for pair in test_pairs:
        normalized = _normalize_pair_for_new_format(pair)
        print(f"   {pair:15} → {normalized}")

def main():
    print("🎯 Pocket Option Signal Parser Tests")
    print("=" * 60)
    
    # Test signal parsing
    parsing_success = test_pocket_signal_parser()
    
    # Test pair normalization
    test_pair_normalization()
    
    print("\n" + "=" * 60)
    if parsing_success:
        print("🎉 ALL TESTS PASSED!")
        print("   Your signal parser is ready to handle Pocket Option bot signals.")
        print("   You can now run your main trading bot to receive and process signals.")
    else:
        print("❌ TESTS FAILED!")
        print("   The signal parser needs to be fixed before running the main bot.")

if __name__ == "__main__":
    main()
