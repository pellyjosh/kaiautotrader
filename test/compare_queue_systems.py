#!/usr/bin/env python3
"""
Demo: Global vs Per-Trade Queue Systems
Demonstrates the difference between current global system and requested per-trade system
"""

class GlobalQueueSystem:
    """Current implementation: ONE global queue, any win resets everything"""
    def __init__(self, base_amount=1.0, multiplier=2.0):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.global_queue = []
        self.consecutive_losses = 0
        
    def get_trade_amount(self):
        if self.global_queue:
            return self.global_queue.pop(0)  # FIFO
        return self.base_amount
    
    def handle_loss(self, trade_id, amount):
        self.consecutive_losses += 1
        next_amount = self.base_amount * (self.multiplier ** self.consecutive_losses)
        self.global_queue.append(next_amount)
        print(f"  Global Loss #{self.consecutive_losses}: Next amount ${next_amount:.2f} added to queue")
        print(f"  Global Queue: {[f'${x:.2f}' for x in self.global_queue]}")
    
    def handle_win(self, trade_id, amount):
        self.global_queue.clear()  # ANY WIN resets EVERYTHING
        self.consecutive_losses = 0
        print(f"  Global Win: Queue CLEARED, back to base ${self.base_amount:.2f}")
        print(f"  Global Queue: {self.global_queue}")


class PerTradeQueueSystem:
    """Requested implementation: Separate queue per trade, only wins reset their own queue"""
    def __init__(self, base_amount=1.0, multiplier=2.0):
        self.base_amount = base_amount
        self.multiplier = multiplier
        self.trade_queues = {}  # trade_id -> [amounts]
        self.trade_losses = {}  # trade_id -> consecutive_losses
        
    def get_trade_amount(self, trade_id):
        if trade_id in self.trade_queues and self.trade_queues[trade_id]:
            return self.trade_queues[trade_id].pop(0)  # FIFO from this trade's queue
        return self.base_amount
    
    def handle_loss(self, trade_id, amount):
        # Initialize if first time
        if trade_id not in self.trade_losses:
            self.trade_losses[trade_id] = 0
            self.trade_queues[trade_id] = []
            
        self.trade_losses[trade_id] += 1
        next_amount = self.base_amount * (self.multiplier ** self.trade_losses[trade_id])
        self.trade_queues[trade_id].append(next_amount)
        
        print(f"  Trade {trade_id} Loss #{self.trade_losses[trade_id]}: Next amount ${next_amount:.2f} added to ITS queue")
        print(f"  Trade {trade_id} Queue: {[f'${x:.2f}' for x in self.trade_queues[trade_id]]}")
    
    def handle_win(self, trade_id, amount):
        # Only reset THIS trade's queue
        if trade_id in self.trade_queues:
            self.trade_queues[trade_id].clear()
        if trade_id in self.trade_losses:
            self.trade_losses[trade_id] = 0
            
        print(f"  Trade {trade_id} Win: Only ITS queue cleared, back to base ${self.base_amount:.2f}")
        print(f"  Trade {trade_id} Queue: {self.trade_queues.get(trade_id, [])}")
        print(f"  Other queues remain: {[(k, [f'${x:.2f}' for x in v]) for k, v in self.trade_queues.items() if k != trade_id and v]}")


def demo_scenario():
    print("🔄 DEMO: 3 Concurrent Trades with Mixed Results")
    print("=" * 70)
    
    # Initialize both systems
    global_sys = GlobalQueueSystem()
    per_trade_sys = PerTradeQueueSystem()
    
    print("\n📊 Scenario: 3 trades start, 2 lose, 1 wins")
    print("-" * 50)
    
    # Phase 1: 3 trades start
    print("\n🎬 Phase 1: 3 trades start")
    print("Global System:")
    g1_amount = global_sys.get_trade_amount()
    g2_amount = global_sys.get_trade_amount()
    g3_amount = global_sys.get_trade_amount()
    print(f"  Trade 1 (EURUSD): ${g1_amount:.2f}")
    print(f"  Trade 2 (GBPUSD): ${g2_amount:.2f}")
    print(f"  Trade 3 (BITCOIN): ${g3_amount:.2f}")
    
    print("\nPer-Trade System:")
    p1_amount = per_trade_sys.get_trade_amount("EURUSD")
    p2_amount = per_trade_sys.get_trade_amount("GBPUSD")
    p3_amount = per_trade_sys.get_trade_amount("BITCOIN")
    print(f"  Trade 1 (EURUSD): ${p1_amount:.2f}")
    print(f"  Trade 2 (GBPUSD): ${p2_amount:.2f}")
    print(f"  Trade 3 (BITCOIN): ${p3_amount:.2f}")
    
    # Phase 2: First 2 trades lose
    print("\n🎬 Phase 2: EURUSD and GBPUSD lose")
    print("Global System:")
    global_sys.handle_loss("EURUSD", g1_amount)
    global_sys.handle_loss("GBPUSD", g2_amount)
    
    print("\nPer-Trade System:")
    per_trade_sys.handle_loss("EURUSD", p1_amount)
    per_trade_sys.handle_loss("GBPUSD", p2_amount)
    
    # Phase 3: BITCOIN wins
    print("\n🎬 Phase 3: BITCOIN wins")
    print("Global System:")
    global_sys.handle_win("BITCOIN", g3_amount)
    
    print("\nPer-Trade System:")
    per_trade_sys.handle_win("BITCOIN", p3_amount)
    
    # Phase 4: New trades arrive
    print("\n🎬 Phase 4: New trades arrive")
    print("Global System:")
    new_g1 = global_sys.get_trade_amount()
    new_g2 = global_sys.get_trade_amount()
    print(f"  New EURUSD trade: ${new_g1:.2f}")
    print(f"  New APPLE trade: ${new_g2:.2f}")
    
    print("\nPer-Trade System:")
    new_p1 = per_trade_sys.get_trade_amount("EURUSD")  # Should use queued amount
    new_p2 = per_trade_sys.get_trade_amount("APPLE")   # Should use base amount
    print(f"  New EURUSD trade: ${new_p1:.2f} (from EURUSD queue)")
    print(f"  New APPLE trade: ${new_p2:.2f} (fresh symbol)")


if __name__ == "__main__":
    demo_scenario()
    
    print("\n" + "=" * 70)
    print("🎯 KEY DIFFERENCES:")
    print("=" * 70)
    print("✅ CURRENT (Global): Any win resets EVERYTHING")
    print("✅ REQUESTED (Per-Trade): Win only resets THAT symbol's queue")
    print("\n🔄 Per-Trade means:")
    print("  - EURUSD builds its own Martingale progression")
    print("  - GBPUSD builds its own Martingale progression")  
    print("  - EURUSD win only resets EURUSD queue")
    print("  - GBPUSD losses don't affect EURUSD progression")
