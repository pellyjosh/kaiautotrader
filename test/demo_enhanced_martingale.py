#!/usr/bin/env python3
"""
Demo script showing how the global queue-based Martingale system handles multiple signals.
This simulates real-world scenarios where signals arrive for any symbol at any time.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import detectsignal
import time

def demo_global_queue_based_martingale():
    """Demonstrate how the global queue-based system works"""
    print("🚀 Global Queue-Based Martingale System Demo")
    print("=" * 70)
    
    # Initialize the system (same as bot.py would do)
    detectsignal.initialize_martingale_system(2.5, enabled=True)
    
    print("📊 Scenario: Mixed signals arrive, some symbols may not repeat")
    print("-" * 70)
    
    # Simulate realistic signal scenario
    scenarios = [
        ("📡 3 signals arrive rapidly", [
            ("EURUSD", "call", "📈 EURUSD bullish"),
            ("GBPUSD", "put", "📉 GBPUSD bearish"), 
            ("BITCOIN_otc", "call", "🟠 Bitcoin signal"),
        ]),
        ("💥 2 trades lose", [
            ("trade_1", "EURUSD", "loss", -1.0),
            ("trade_2", "GBPUSD", "loss", -1.0),
        ]),
        ("📡 2 new signals (different symbols)", [
            ("GOLD_otc", "put", "🥇 Gold bearish"),
            ("USDJPY", "call", "� USD/JPY bullish"),
        ]),
        ("🎯 Mixed results", [
            ("trade_3", "BITCOIN_otc", "win", 1.8),  # This should reset everything
        ]),
        ("📡 Fresh signals after reset", [
            ("TESLA_otc", "call", "🚗 Tesla signal"),
            ("APPLE_otc", "put", "🍎 Apple signal"),
        ]),
    ]
    
    print("🔄 Processing scenarios...")
    print()
    
    for scenario_name, actions in scenarios:
        print(f"🎬 {scenario_name}")
        
        if "signals arrive" in scenario_name:
            # Process new signals
            for symbol, direction, description in actions:
                amount = detectsignal._get_trade_amount_for_new_signal()
                print(f"  → {description}: {symbol} {direction.upper()} ${amount}")
        
        elif "lose" in scenario_name or "results" in scenario_name:
            # Process trade results
            for trade_id, symbol, result, pnl in actions:
                detectsignal._handle_trade_result(trade_id, symbol, result, pnl)
                result_icon = "✅" if result == "win" else "❌"
                print(f"  → {result_icon} {symbol} {result.upper()} (P&L: ${pnl})")
        
        # Show status after each scenario
        status = detectsignal.get_current_martingale_status()
        print(f"     Status: Losses={status['consecutive_losses']}, Queue={status['queued_amounts']}, Active={status['active_trades_count']}")
        print()
    
    print("� Final System Analysis:")
    print("-" * 70)
    
    final_status = detectsignal.get_current_martingale_status()
    print(f"✅ Consecutive Losses: {final_status['consecutive_losses']}")
    print(f"✅ Queued Amounts: {final_status['queued_amounts']}")
    print(f"✅ Active Trades: {final_status['active_trades_count']}")
    print()
    
    print("🎯 Key Benefits of Global Queue-Based System:")
    print("=" * 70)
    print("✅ Works with ANY symbol - no symbol-specific tracking needed")
    print("✅ Queues Martingale amounts for next trades regardless of symbol")  
    print("✅ Handles concurrent trades perfectly")
    print("✅ Any win resets the entire system globally")
    print("✅ Perfect for bots that trade different symbols unpredictably")
    print("✅ Simpler logic - just tracks global wins/losses")
    print()
    
    print("� Real-World Example Flow:")
    print("=" * 70)
    
    # Clear and demo a realistic flow
    detectsignal._consecutive_losses = 0
    detectsignal._martingale_queue.clear()
    detectsignal._active_trades_count = 0
    
    example_flow = [
        "1️⃣ EURUSD signal arrives → $1.00 (fresh start)",
        "2️⃣ GOLD signal arrives → $1.00 (fresh start)", 
        "3️⃣ EURUSD loses → Queue $2.50 for next trade",
        "4️⃣ BITCOIN signal arrives → $2.50 (from queue)",
        "5️⃣ GOLD loses → Queue $6.25 for next trade",  
        "6️⃣ APPLE signal arrives → $6.25 (from queue)",
        "7️⃣ BITCOIN wins → Reset everything, clear queue",
        "8️⃣ Any new signal → $1.00 (fresh start)",
    ]
    
    for step in example_flow:
        print(f"  {step}")
    
    print()
    print("🚨 Risk Management:")
    print("=" * 70)
    print("⚠️  Monitor total queued exposure")
    print("⚠️  Queue can build up with multiple consecutive losses") 
    print("⚠️  Any single win clears the entire queue")
    print("⚠️  Enable/disable toggle works instantly")

def demo_queue_buildup_scenario():
    """Demonstrate how the queue builds up with multiple losses"""
    print("\n" + "="*70)
    print("📊 Queue Buildup Demonstration")
    print("="*70)
    
    # Reset system
    detectsignal._consecutive_losses = 0
    detectsignal._martingale_queue.clear()
    detectsignal._active_trades_count = 0
    
    print("🎯 Scenario: Multiple losses create queue buildup")
    print()
    
    # Start 5 trades
    trade_amounts = []
    symbols = ["EURUSD", "GBPUSD", "GOLD_otc", "BITCOIN_otc", "APPLE_otc"]
    
    print("📡 5 signals arrive:")
    for i, symbol in enumerate(symbols, 1):
        amount = detectsignal._get_trade_amount_for_new_signal()
        trade_amounts.append(amount)
        print(f"  {i}. {symbol}: ${amount}")
    
    print(f"\n� All start at ${trade_amounts[0]} (no losses yet)")
    
    # Now all 5 lose
    print("\n💥 All 5 trades lose:")
    for i, symbol in enumerate(symbols, 1):
        trade_id = f"trade_{i}"
        detectsignal._handle_trade_result(trade_id, symbol, "loss", -trade_amounts[i-1])
        status = detectsignal.get_current_martingale_status()
        print(f"  {i}. {symbol} loses → Queue: {status['queued_amounts']}")
    
    final_status = detectsignal.get_current_martingale_status()
    total_queued = sum(final_status['queued_amounts'])
    print(f"\n📈 Final Queue: {final_status['queued_amounts']}")
    print(f"💰 Total Queued Exposure: ${total_queued:.2f}")
    print(f"🔢 Consecutive Losses: {final_status['consecutive_losses']}")
    
    # Show what happens with new signals
    print(f"\n📡 Next 3 signals will use queued amounts:")
    for i in range(3):
        amount = detectsignal._get_trade_amount_for_new_signal()
        remaining_status = detectsignal.get_current_martingale_status()
        print(f"  Signal {i+1}: ${amount} (queue remaining: {remaining_status['queued_amounts']})")
    
    print(f"\n🎯 Key Insight: Queue preserves exact Martingale progression!")

if __name__ == "__main__":
    demo_global_queue_based_martingale()
    demo_queue_buildup_scenario()
