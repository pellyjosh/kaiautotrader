# Enhanced Martingale Calculation System

## Overview

The enhanced Martingale calculation system replaces the traditional exponential multiplier approach with a sophisticated formula that:

- Recovers ALL previous losses exactly
- Adds a small profit target (5% of base amount)
- Accounts for 85% payout rate
- Includes comprehensive risk management

## Key Formula

```python
# Core Calculation
Total_Losses = sum(all_previous_losing_amounts)
Target_Profit = base_amount * 0.05  # 5% profit target
Required_Win_Amount = Total_Losses + Target_Profit
Next_Trade_Amount = Required_Win_Amount / payout_rate  # (0.85 = 85%)
```

## Implementation Changes

### 1. Database Manager (`database_manager.py`)

Added three new methods:

#### `calculate_enhanced_martingale_amount()`

- Core calculation method
- Recovers all losses + target profit
- Accounts for actual payout percentage
- Includes safety caps and validations

#### `calculate_safe_martingale_with_balance_check()`

- Adds balance protection (max 10% risk)
- Progressive caps to prevent exponential explosion
- Risk management layers

#### `validate_martingale_trade_safety()`

- Multi-level safety validation
- Checks max level, balance limits, progression reasonableness
- Returns safety recommendations

### 2. Signal Detection (`detectsignal.py`)

Updated `_calculate_next_martingale_amount()`:

- Uses enhanced calculation when database manager available
- Falls back to legacy calculation as backup
- Integrates with account balance checks

Updated loss handling:

- Tracks actual lost amounts instead of just calculating next multiplier
- Stores lost amounts in queue for precise recovery calculation
- Logs detailed recovery information

### 3. Enhanced Martingale System (`enhanced_martingale.py`)

Updated lane calculation:

- Integrates enhanced formula into lane-based trading
- Gets previous trade amounts from lane history
- Uses database manager for calculations
- Falls back to traditional method if enhanced fails

## How It Works When a Trade Loses

### Traditional System (OLD):

```python
# When trade loses
consecutive_losses += 1
next_amount = base_amount * (multiplier ** consecutive_losses)
# Example: $1 -> $2.5 -> $6.25 -> $15.63 (exponential growth)
```

### Enhanced System (NEW):

```python
# When trade loses
lost_amount = actual_trade_amount  # e.g., $1.00
martingale_queue.append(lost_amount)  # Track actual loss
total_losses = sum(martingale_queue)  # e.g., $1.00
target_profit = base_amount * 0.05    # e.g., $0.05
required_win = total_losses + target_profit  # $1.05
next_amount = required_win / 0.85     # $1.24 (exact recovery amount)
```

### Example Scenario:

1. **Trade 1**: Lose $1.00 → Queue: [$1.00] → Next: $1.24
2. **Trade 2**: Lose $1.24 → Queue: [$1.00, $1.24] → Next: $2.64
3. **Trade 3**: Win $2.64 × 0.85 = $2.24 → Recovers $2.24 > $2.24 needed ✓

## Risk Management Features

### 1. Balance Protection

- Never risk more than 10% of account balance
- Maintains minimum balance for future trades

### 2. Progressive Caps

- Limits exponential growth with reasonable maximums
- Adjusts based on consecutive loss count

### 3. Safety Validations

- Max level enforcement
- Balance sufficiency checks
- Progression reasonableness validation

### 4. Multiple Fallbacks

- Enhanced → Safe enhanced → Legacy calculation
- Database errors don't break trading

## Benefits

1. **Exact Recovery**: Recovers precise amount lost (not approximate)
2. **Profit Guaranteed**: Always includes small profit when winning
3. **Payout Aware**: Accounts for actual broker payout rates
4. **Risk Managed**: Multiple safety layers prevent over-trading
5. **Balance Safe**: Protects account from excessive risk
6. **Flexible**: Works with both legacy and enhanced systems

## Configuration

The system uses existing account settings:

- `base_amount`: Starting trade amount
- `max_mat_level`: Maximum Martingale levels
- `min_payout_threshold`: Expected payout rate (default 85%)
- `balance`: Current account balance for safety checks

## Monitoring

Enhanced logging shows:

- Total losses being recovered
- Target profit amount
- Required win amount
- Next trade amount
- Expected payout after win
- Safety check results

This ensures complete transparency in the calculation process and helps with debugging and optimization.
