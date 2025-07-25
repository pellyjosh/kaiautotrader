#!/usr/bin/env python3
"""
Test script for global queue-based Martingale system functionality.
Tests global loss tracking and queue-based amount assignment.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import detectsignal

def test_global_martingale_logic():
    """Test the global Martingale system logic"""
    print("Testing Global Queue-Based Martingale System Logic")
    print("=" * 60)
    
    # Initialize with 2.5x multiplier (same as bot.py)
    detectsignal.initialize_martingale_system(2.5, enabled=True)
    
    # Test initial state
    status = detectsignal.get_current_martingale_status()
    print(f"Initial Status: {status}")
    assert status['martingale_enabled'] == True
    assert status['consecutive_losses'] == 0
    assert status['queue_length'] == 0
    
    # Simulate first trade
    amount1 = detectsignal._get_trade_amount_for_new_signal()
    print(f"First trade amount: ${amount1}")
    assert amount1 == 1.0
    
    # Simulate loss
    detectsignal._handle_trade_result("trade_1", "EURUSD", "loss", -1.0)
    status = detectsignal.get_current_martingale_status()
    print(f"After first loss: {status}")
    assert status['consecutive_losses'] == 1
    assert status['queue_length'] == 1  # Should have one queued amount
    assert status['queued_amounts'][0] == 2.5  # 1.0 * 2.5^1
    
    # Get next trade amount (should come from queue)
    amount2 = detectsignal._get_trade_amount_for_new_signal()
    print(f"Second trade amount: ${amount2}")
    assert amount2 == 2.5
    
    # Queue should now be empty
    status = detectsignal.get_current_martingale_status()
    assert status['queue_length'] == 0
    
    # Simulate win - should reset and clear queue
    detectsignal._handle_trade_result("trade_2", "GBPUSD", "win", 2.5)
    status = detectsignal.get_current_martingale_status()
    print(f"After win: {status}")
    assert status['consecutive_losses'] == 0
    assert status['queue_length'] == 0
    
    print("✅ Global Martingale basic tests passed!")

def test_concurrent_trades_scenario():
    """Test concurrent trades and queue management"""
    print("\nTesting Concurrent Trades Scenario")
    print("=" * 60)
    
    # Clear previous state
    detectsignal._consecutive_losses = 0
    detectsignal._martingale_queue.clear()
    detectsignal._active_trades_count = 0
    
    # Simulate multiple signals arriving quickly
    print("📡 Signals arriving rapidly...")
    amounts = []
    for i in range(3):
        amount = detectsignal._get_trade_amount_for_new_signal()
        amounts.append(amount)
        print(f"Signal {i+1}: ${amount}")
    
    # All should be $1.00 initially (no losses yet)
    assert all(amount == 1.0 for amount in amounts)
    
    status = detectsignal.get_current_martingale_status()
    print(f"Status after 3 concurrent signals: Active trades: {status['active_trades_count']}")
    assert status['active_trades_count'] == 3
    
    # First two trades lose
    print("\n💥 First two trades lose...")
    detectsignal._handle_trade_result("trade_1", "EURUSD", "loss", -1.0)
    detectsignal._handle_trade_result("trade_2", "GBPUSD", "loss", -1.0)
    
    status = detectsignal.get_current_martingale_status()
    print(f"After 2 losses: Consecutive losses: {status['consecutive_losses']}, Queue: {status['queued_amounts']}")
    assert status['consecutive_losses'] == 2
    assert status['queue_length'] == 2
    assert status['queued_amounts'][0] == 2.5   # First queued amount
    assert status['queued_amounts'][1] == 6.25  # Second queued amount (2.5^2)
    
    # Two new signals arrive - should use queued amounts
    print("\n📡 Two new signals arrive...")
    amount_new1 = detectsignal._get_trade_amount_for_new_signal()
    amount_new2 = detectsignal._get_trade_amount_for_new_signal()
    print(f"New signal 1: ${amount_new1}")
    print(f"New signal 2: ${amount_new2}")
    
    assert amount_new1 == 2.5   # From queue
    assert amount_new2 == 6.25  # From queue
    
    # Queue should now be empty
    status = detectsignal.get_current_martingale_status()
    assert status['queue_length'] == 0
    
    print("✅ Concurrent trades test passed!")

def test_martingale_enable_disable():
    """Test enabling and disabling Martingale system"""
    print("\nTesting Martingale Enable/Disable")
    print("=" * 60)
    
    # Clear previous state
    detectsignal._consecutive_losses = 0
    detectsignal._martingale_queue.clear()
    detectsignal._active_trades_count = 0
    
    # Test with Martingale enabled
    detectsignal.set_martingale_enabled(True)
    
    amount_enabled = detectsignal._get_trade_amount_for_new_signal()
    print(f"Amount with Martingale ENABLED: ${amount_enabled}")
    assert amount_enabled == 1.0
    
    # Simulate loss
    detectsignal._handle_trade_result("test_1", "TESTPAIR", "loss", -1.0)
    status = detectsignal.get_current_martingale_status()
    print(f"After loss (ENABLED): {status}")
    assert status['consecutive_losses'] == 1
    assert status['queue_length'] == 1
    
    # Disable Martingale
    detectsignal.set_martingale_enabled(False)
    amount_disabled = detectsignal._get_trade_amount_for_new_signal()
    print(f"Amount with Martingale DISABLED: ${amount_disabled}")
    assert amount_disabled == 1.0  # Should always be default when disabled
    
    # Another loss while disabled - should not affect anything
    detectsignal._handle_trade_result("test_2", "TESTPAIR", "loss", -1.0)
    status = detectsignal.get_current_martingale_status()
    print(f"After loss (DISABLED): {status}")
    assert status['consecutive_losses'] == 1  # Should not increase
    assert status['queue_length'] == 1       # Should not change
    
    # Re-enable and check if state is preserved
    detectsignal.set_martingale_enabled(True)
    amount_from_queue = detectsignal._get_trade_amount_for_new_signal()
    print(f"Amount after re-enabling (from queue): ${amount_from_queue}")
    assert amount_from_queue == 2.5  # Should use the queued amount
    
    print("✅ Enable/Disable test passed!")

def test_mixed_results_scenario():
    """Test mixed win/loss scenarios"""
    print("\nTesting Mixed Results Scenario")
    print("=" * 60)
    
    # Clear previous state
    detectsignal._consecutive_losses = 0
    detectsignal._martingale_queue.clear()
    detectsignal._active_trades_count = 0
    
    # Start with 3 trades
    amounts = [detectsignal._get_trade_amount_for_new_signal() for _ in range(3)]
    print(f"Started 3 trades: {amounts}")
    
    # 2 lose, 1 wins
    detectsignal._handle_trade_result("trade_1", "PAIR1", "loss", -1.0)
    detectsignal._handle_trade_result("trade_2", "PAIR2", "loss", -1.0)
    detectsignal._handle_trade_result("trade_3", "PAIR3", "win", 1.0)  # This should reset everything
    
    status = detectsignal.get_current_martingale_status()
    print(f"After 2 losses + 1 win: {status}")
    assert status['consecutive_losses'] == 0  # Reset by win
    assert status['queue_length'] == 0       # Cleared by win
    
    # Next trade should be fresh
    next_amount = detectsignal._get_trade_amount_for_new_signal()
    print(f"Next trade after win: ${next_amount}")
    assert next_amount == 1.0
    
    print("✅ Mixed results test passed!")

if __name__ == "__main__":
    test_global_martingale_logic()
    test_concurrent_trades_scenario()
    test_martingale_enable_disable()
    test_mixed_results_scenario()
    
    print("\n🎉 All Global Queue-Based Martingale Tests Passed!")
    print("\nFeatures tested:")
    print("- ✅ Global loss tracking (not per-symbol)")
    print("- ✅ Queue-based amount assignment")
    print("- ✅ Concurrent trade handling")
    print("- ✅ Enable/disable toggle")
    print("- ✅ Win resets entire system")
    print("- ✅ FIFO queue for Martingale amounts")
