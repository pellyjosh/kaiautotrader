# Enhanced Martingale Lane Creation Fix

## Problem Identified

When a base trade failed and a new Martingale lane was created, the system was **not recording the failed trade** as part of the lane. This caused:

1. **Lost trade history** - The failed trade that triggered the lane wasn't tracked
2. **Incorrect Martingale progression** - The lane started "fresh" without accounting for the loss
3. **Missing investment tracking** - Total invested amount didn't include the failed base trade

## Solution Implemented

### Updated `_create_new_lane_for_loss()` Method

**Before**:

```python
def _create_new_lane_for_loss(self, account_name: str, symbol: str, account_settings: Dict) -> bool:
    # Create lane
    lane_id = self.db_manager.create_martingale_lane(...)
    # Lane created but failed trade not recorded
```

**After**:

```python
def _create_new_lane_for_loss(self, account_name: str, symbol: str, account_settings: Dict,
                             failed_trade_id: str = None, failed_amount: float = 0.0) -> bool:
    # Create lane
    lane_id = self.db_manager.create_martingale_lane(...)

    # Record the failed trade that triggered this lane creation
    if failed_trade_id and failed_amount > 0:
        self.db_manager.update_martingale_lane_on_trade(
            lane_id, failed_trade_id, failed_amount, 0.0
        )
```

### Updated `_handle_losing_trade()` Method

**Before**:

```python
return self._create_new_lane_for_loss(account_name, symbol, account_settings)
```

**After**:

```python
return self._create_new_lane_for_loss(account_name, symbol, account_settings, trade_id, amount)
```

## Expected Behavior After Fix

### Scenario: Base Trade Loss → Lane Creation

1. **Signal arrives**: Place base trade ($1.00)
2. **Trade fails**: Loss recorded in database
3. **Lane created**: New Martingale lane created for the symbol
4. **Failed trade recorded**: The $1.00 failed trade is added to the lane's trade history
5. **Lane state updated**:
   - `current_level`: 1 (ready for next Martingale level)
   - `total_invested`: $1.00 (includes the failed trade)
   - `trade_ids`: [`failed_trade_id`]
6. **Next signal**: Gets assigned to lane at Level 1 ($1.50)

### Lane Progression Example

| Step | Action               | Trade Amount | Lane Level | Total Invested | Trade IDs                         |
| ---- | -------------------- | ------------ | ---------- | -------------- | --------------------------------- |
| 1    | Base trade fails     | $1.00        | N/A        | -              | -                                 |
| 2    | Lane created         | -            | 0→1        | $1.00          | [trade_001]                       |
| 3    | Next signal assigned | $1.50        | 1→2        | $2.50          | [trade_001, trade_002]            |
| 4    | If fails again       | $2.25        | 2→3        | $4.75          | [trade_001, trade_002, trade_003] |

## Benefits

1. **Complete Trade History**: All trades (including the triggering failure) are tracked
2. **Accurate Investment Tracking**: `total_invested` includes the failed base trade
3. **Proper Martingale Progression**: Lane level reflects the actual number of losses
4. **Better Analytics**: Full sequence visible for performance analysis

## What You'll See in Logs

### Before Fix:

```
[INFO]: [EnhancedMartingale] [pelly_demo] Created new Martingale lane lane_123 for EURUSD_otc
```

### After Fix:

```
[INFO]: [EnhancedMartingale] [pelly_demo] Created new Martingale lane lane_123 for EURUSD_otc
[INFO]: [EnhancedMartingale] [pelly_demo] Recorded failed trade abc-123 ($1.00) in new lane lane_123
```

## Database Impact

The `martingale_lanes` table will now properly show:

- **trade_ids**: Includes the failed trade that triggered lane creation
- **total_invested**: Includes the failed trade amount
- **current_level**: Correctly set to 1 after recording the failed trade

This ensures the Martingale system has complete visibility into the trading sequence and can make proper decisions for future trades.
